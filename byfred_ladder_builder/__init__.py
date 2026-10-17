"""
Byfred Ladder Builder
---------------------
Génère une échelle GTA V / FiveM prête à exporter avec Sollumz :
  - le modèle 3D (Drawable + Model, shader default.sps, texture intégrée en DDS)
  - la collision embarquée (Bound Composite -> BVH -> poly triangles)
  - le YTYP : archetype + extension CExtensionDefLadder (top / bottom / normal)

Panneau : Vue 3D > barre latérale (N) > onglet "Sollumz Tools" > Byfred Ladder Builder
Nécessite Sollumz (2.x) activé.
"""

bl_info = {
    "name": "Byfred Ladder Builder",
    "author": "byfredQC",
    "version": (1, 2, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar (N) > Sollumz Tools > Byfred Ladder Builder",
    "description": "GTA V ladder generator (3D + collision + YTYP Ladder extension) for Sollumz / Générateur d'échelles GTA V",
    "category": "Import-Export",
}

import importlib
import math
import os
import random
import struct

import bpy
import bmesh
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from mathutils import Matrix, Vector

from .i18n import T, enum_items


# --------------------------------------------------------------------------- #
#  Accès à Sollumz
# --------------------------------------------------------------------------- #

def _sollumz_package():
    """Nom du package Sollumz (addon classique ou extension Blender 4.2+)."""
    for name in bpy.context.preferences.addons.keys():
        short = name.rsplit(".", 1)[-1].lower()
        if short.startswith("sollumz") and "ladder" not in short:
            return name
    return None


def _sz(module):
    pkg = _sollumz_package()
    if pkg is None:
        raise RuntimeError(T("msg_no_sollumz"))
    return importlib.import_module(f"{pkg}.{module}")


# Valeurs internes Sollumz (chaînes stables)
SZ_DRAWABLE = "sollumz_drawable"
SZ_DRAWABLE_MODEL = "sollumz_drawable_model"
SZ_BOUND_COMPOSITE = "sollumz_bound_composite"
SZ_BOUND_BVH = "sollumz_bound_geometrybvh"
SZ_BOUND_POLY_TRI = "sollumz_bound_poly_triangle"
SZ_EXT_LADDER = "CExtensionDefLadder"


# --------------------------------------------------------------------------- #
#  Propriétés
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
#  Mise à jour en temps réel
# --------------------------------------------------------------------------- #

def _live_update(self, context):
    if not self.live_update:
        return
    drawable = bpy.data.objects.get(self.name.strip())
    if drawable is None or drawable.sollum_type != SZ_DRAWABLE:
        return
    try:
        refresh_geometry(self, drawable)
        refresh_extensions(context.scene, self)
    except Exception as e:
        print("[Byfred Ladder Builder] mise à jour temps réel :", e)


def _live_ext_update(self, context):
    if self.live_update:
        refresh_extensions(context.scene, self)


class LadderBuilderSettings(bpy.types.PropertyGroup):
    name: StringProperty(name="Nom", default="prop_custom_ladder",
                         description="Nom du modèle (ydr) et de l'archetype")

    live_update: BoolProperty(name="Temps réel", default=True,
                              description="Met à jour l'échelle déjà créée (même nom) dès qu'un réglage change")

    # Dimensions
    height: FloatProperty(update=_live_update, name="Hauteur à grimper", default=4.0, min=0.5, max=100.0, unit="LENGTH",
                          description="Du sol jusqu'au niveau où l'on descend en haut (plateforme)")
    top_extension: FloatProperty(update=_live_update, name="Dépassement haut", default=1.0, min=0.0, max=3.0, unit="LENGTH",
                                 description="Longueur des montants au-dessus du point de sortie (pour se tenir)")
    width: FloatProperty(update=_live_update, name="Largeur", default=0.5, min=0.2, max=2.0, unit="LENGTH",
                         description="Distance entre les deux montants (axe à axe)")
    rung_spacing: FloatProperty(update=_live_update, name="Espacement barreaux", default=0.3, min=0.15, max=0.6, unit="LENGTH")
    rungs_to_top: BoolProperty(update=_live_update, name="Barreaux jusqu'en haut", default=True,
                               description="Met des barreaux sur toute la longueur des montants (sinon ils s'arrêtent à la hauteur à grimper)")
    first_rung: FloatProperty(update=_live_update, name="1er barreau", default=0.3, min=0.05, max=1.0, unit="LENGTH",
                              description="Hauteur du premier barreau depuis le sol")

    # Profil
    profile: EnumProperty(update=_live_update, name="Profil / Profile", items=enum_items("profile"), default=0)
    rail_size: FloatProperty(update=_live_update, name="Épaisseur montant", default=0.05, min=0.01, max=0.3, unit="LENGTH")
    rung_size: FloatProperty(update=_live_update, name="Épaisseur barreau", default=0.03, min=0.01, max=0.2, unit="LENGTH")
    segments: IntProperty(update=_live_update, name="Segments (rond)", default=10, min=4, max=32)

    # Accessoires
    wall_brackets: BoolProperty(update=_live_update, name="Fixations murales", default=True,
                                description="Pattes de fixation vers le mur (côté opposé au grimpeur)")
    wall_offset: FloatProperty(update=_live_update, name="Distance au mur", default=0.18, min=0.0, max=1.0, unit="LENGTH")
    cage: BoolProperty(update=_live_update, name="Crinoline (cage)", default=False,
                       description="Arceaux de sécurité côté grimpeur")
    cage_start: FloatProperty(update=_live_update, name="Début cage", default=2.2, min=0.5, max=10.0, unit="LENGTH")
    cage_radius: FloatProperty(update=_live_update, name="Rayon cage", default=0.38, min=0.25, max=1.0, unit="LENGTH")
    cage_spacing: FloatProperty(update=_live_update, name="Espacement arceaux", default=0.9, min=0.3, max=3.0, unit="LENGTH")

    # Côté d'accès
    access_side: EnumProperty(update=_live_update, name="Côté grimpeur / Climber side", items=enum_items("access_side"), default=0,
                              description="Côté où se place le joueur / Side where the player stands")

    # Matériaux / texture
    color: FloatVectorProperty(name="Couleur", subtype="COLOR", size=3, min=0.0, max=1.0,
                               default=(0.55, 0.57, 0.60))
    embed_texture: BoolProperty(name="Texture intégrée (DDS)", default=True,
                                description="Génère une texture métal DDS embarquée dans le .ydr (pas besoin de .ytd)")
    collision_material: EnumProperty(name="Matériau collision / Collision material", items=enum_items("collision_material"), default=0)

    # YTYP / Ladder extension
    ladder_material: EnumProperty(update=_live_ext_update, name="Type échelle / Ladder type", items=enum_items("ladder_material"), default=0)
    can_get_off_top: BoolProperty(update=_live_ext_update, name="Sortie en haut", default=True)
    can_get_off_bottom: BoolProperty(update=_live_ext_update, name="Sortie en bas", default=True)
    lod_dist: FloatProperty(update=_live_ext_update, name="LOD Distance", default=150.0, min=10.0, max=2000.0)
    ytyp_mode: EnumProperty(name="YTYP", items=enum_items("ytyp_mode"), default=0)
    ytyp_name: StringProperty(name="Nom YTYP", default="custom_ladders")
    replace_existing: BoolProperty(name="Remplacer si existe", default=True,
                                   description="Supprime l'ancienne échelle du même nom et son archetype")


# --------------------------------------------------------------------------- #
#  Géométrie
# --------------------------------------------------------------------------- #

def _orient_matrix(start: Vector, end: Vector) -> Matrix:
    """Matrice qui place un cylindre/cube (axe Z, centré) entre start et end."""
    d = end - start
    length = d.length
    rot = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix().to_4x4()
    return Matrix.Translation((start + end) / 2) @ rot, length


def _add_bar(bm, start, end, size, profile, segments):
    mat, length = _orient_matrix(Vector(start), Vector(end))
    if profile == "ROUND":
        bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments,
                              radius1=size / 2, radius2=size / 2, depth=length,
                              matrix=mat, calc_uvs=True)
    else:
        scale = Matrix.Diagonal((size, size, length, 1.0))
        bmesh.ops.create_cube(bm, size=1.0, matrix=mat @ scale, calc_uvs=True)


def _add_box(bm, center, dims):
    m = Matrix.Translation(Vector(center)) @ Matrix.Diagonal((*dims, 1.0))
    bmesh.ops.create_cube(bm, size=1.0, matrix=m, calc_uvs=True)


def _ladder_layout(s):
    """Positions utiles (tout en espace local, origine = pied de l'échelle, centre)."""
    climber = -1.0 if s.access_side == "NEG_Y" else 1.0  # direction du grimpeur sur Y
    half = s.width / 2
    rail_top = s.height + s.top_extension
    rungs = []
    z = s.first_rung
    limit = (rail_top - min(0.08, s.rung_spacing / 2)) if s.rungs_to_top else s.height
    while z <= limit + 1e-4:
        rungs.append(z)
        z += s.rung_spacing
    return climber, half, rail_top, rungs


def build_visual_mesh(s, name):
    climber, half, rail_top, rungs = _ladder_layout(s)
    bm = bmesh.new()

    # Montants
    for x in (-half, half):
        _add_bar(bm, (x, 0, 0), (x, 0, rail_top), s.rail_size, s.profile, s.segments)

    # Barreaux (légèrement rentrés dans les montants)
    for z in rungs:
        _add_bar(bm, (-half, 0, z), (half, 0, z), s.rung_size, s.profile, max(6, s.segments - 2))

    # Fixations murales (côté opposé au grimpeur)
    if s.wall_brackets and s.wall_offset > 0.01:
        wall_dir = -climber
        bz = [min(0.15, rail_top * 0.1)]
        nb = max(2, int(rail_top / 2.0) + 1)
        for i in range(1, nb):
            bz.append(rail_top * i / (nb - 1) - 0.15)
        for z in bz:
            for x in (-half, half):
                y0 = 0.0
                y1 = wall_dir * s.wall_offset
                _add_box(bm, (x, (y0 + y1) / 2, z), (s.rail_size * 0.8, abs(y1 - y0), s.rail_size * 0.8))
                # platine
                _add_box(bm, (x, y1, z), (s.rail_size * 2.2, 0.01, s.rail_size * 2.6))

    # Crinoline
    if s.cage and s.cage_start < rail_top - 0.2:
        r = s.cage_radius
        cy = climber * r  # centre de la cage côté grimpeur
        hoop_zs = []
        z = s.cage_start
        while z <= rail_top + 1e-4:
            hoop_zs.append(z)
            z += s.cage_spacing
        if not hoop_zs or rail_top - hoop_zs[-1] > 0.2:
            hoop_zs.append(rail_top)
        seg = 14
        rad = max(math.hypot(half, cy), r)
        a0 = math.atan2(-cy, -half)          # angle du montant gauche vu du centre de cage
        a1 = math.atan2(-cy, half)           # angle du montant droit
        ccw = (a1 - a0) % (2 * math.pi)
        # on garde l'arc qui passe côté grimpeur (dos du joueur)
        if math.sin(a0 + ccw / 2) * climber > 0:
            sweep = ccw
        else:
            sweep = ccw - 2 * math.pi

        def arc_point(frac, z):
            a = a0 + sweep * frac
            return (rad * math.cos(a), cy + rad * math.sin(a), z)

        for z in hoop_zs:
            pts = [arc_point(i / seg, z) for i in range(seg + 1)]
            for p0, p1 in zip(pts[:-1], pts[1:]):
                _add_bar(bm, p0, p1, s.rung_size * 1.4, "SQUARE", 4)
        # lisses verticales
        z0, z1 = hoop_zs[0], hoop_zs[-1]
        for frac in (0.2, 0.4, 0.6, 0.8):
            _add_bar(bm, arc_point(frac, z0), arc_point(frac, z1), s.rung_size * 1.2, "SQUARE", 4)

    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for p in mesh.polygons:
        p.use_smooth = s.profile == "ROUND"
    return mesh


def build_collision_mesh(s, name):
    """Collision simplifiée en boîtes (montants + barreaux + fixations)."""
    climber, half, rail_top, rungs = _ladder_layout(s)
    bm = bmesh.new()
    t = max(s.rail_size, 0.04)
    for x in (-half, half):
        _add_box(bm, (x, 0, rail_top / 2), (t, t, rail_top))
    rt = max(s.rung_size, 0.03)
    for z in rungs:
        _add_box(bm, (0, 0, z), (s.width, rt, rt))
    if s.wall_brackets and s.wall_offset > 0.01:
        wall_dir = -climber
        _add_box(bm, (-half, wall_dir * s.wall_offset / 2, rail_top - 0.15), (t, s.wall_offset, t))
        _add_box(bm, (half, wall_dir * s.wall_offset / 2, rail_top - 0.15), (t, s.wall_offset, t))
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    return mesh


# --------------------------------------------------------------------------- #
#  Texture DDS (A8R8G8B8 non compressé, avec mipmaps)
# --------------------------------------------------------------------------- #

def _write_dds(path, size, color):
    rnd = random.Random(1337)
    base = [int(max(0.0, min(1.0, c)) * 255) for c in color]
    # métal brossé : bruit horizontal + léger grain
    rows = []
    for y in range(size):
        line_n = rnd.uniform(-14, 14)
        row = []
        for x in range(size):
            n = line_n + rnd.uniform(-6, 6)
            row.append(tuple(max(0, min(255, int(b + n))) for b in base))
        rows.append(row)

    levels = [rows]
    while len(levels[-1]) > 1:
        prev = levels[-1]
        h = len(prev) // 2
        nxt = []
        for y in range(h):
            r = []
            for x in range(h):
                px = [prev[2 * y][2 * x], prev[2 * y][2 * x + 1], prev[2 * y + 1][2 * x], prev[2 * y + 1][2 * x + 1]]
                r.append(tuple(sum(p[i] for p in px) // 4 for i in range(3)))
            nxt.append(r)
        levels.append(nxt)

    flags = 0x1 | 0x2 | 0x4 | 0x8 | 0x1000 | 0x20000  # CAPS|HEIGHT|WIDTH|PITCH|PIXELFORMAT|MIPMAPCOUNT
    header = struct.pack("<4s", b"DDS ")
    header += struct.pack("<7I", 124, flags, size, size, size * 4, 0, len(levels))
    header += struct.pack("<11I", *([0] * 11))
    header += struct.pack("<8I", 32, 0x41, 0, 32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000)
    header += struct.pack("<5I", 0x1000 | 0x8 | 0x400000, 0, 0, 0, 0)

    data = bytearray()
    for lvl in levels:
        for row in lvl:
            for r, g, b in row:
                data += bytes((b, g, r, 255))  # BGRA
    with open(path, "wb") as f:
        f.write(header)
        f.write(data)


def create_ladder_material(s, name, obj):
    shader_materials = _sz("ydr.shader_materials")
    mat_ops = _sz("ydr.operators.materials")

    mat = shader_materials.create_shader("default.sps")
    mat.name = f"{name}_mat"
    obj.data.materials.append(mat)

    tex_node = None
    for n in mat.node_tree.nodes:
        if isinstance(n, bpy.types.ShaderNodeTexImage) and n.name == "DiffuseSampler":
            tex_node = n
            break

    if tex_node is not None:
        if s.embed_texture:
            tex_name = f"{name}_d"
            folder = bpy.app.tempdir or os.path.dirname(bpy.data.filepath) or os.getcwd()
            path = os.path.join(folder, f"{tex_name}.dds")
            _write_dds(path, 128, s.color)
            img = bpy.data.images.load(path, check_existing=False)
            img.name = tex_name
            try:
                img.pack()
            except Exception:
                pass
            tex_node.image = img
            try:
                tex_node.texture_properties.embedded = True
            except Exception:
                pass

    mat_ops.post_create_shader_add_default_images(mat)
    mat_ops.post_create_shader_update_object(obj, mat)
    return mat


def create_collision_material(s):
    cm = _sz("ybn.collision_materials")
    idx = 0
    for i, m in enumerate(cm.collisionmats):
        if m.name == s.collision_material:
            idx = i
            break
    return cm.create_collision_material_from_index(idx)


# --------------------------------------------------------------------------- #
#  Hiérarchie Sollumz
# --------------------------------------------------------------------------- #

GENERAL_FLAGS1 = ("map_weapon", "map_dynamic", "map_animal", "map_cover", "map_vehicle")
GENERAL_FLAGS2 = ("vehicle_not_bvh", "vehicle_bvh", "ped", "ragdoll", "animal", "animal_ragdoll", "object",
                  "plant", "projectile", "explosion", "forklift_forks", "test_weapon", "test_camera",
                  "test_ai", "test_script", "test_vehicle_wheel", "glass")


def _set_flags(obj):
    for f in GENERAL_FLAGS1:
        if hasattr(obj.composite_flags1, f):
            setattr(obj.composite_flags1, f, True)
    for f in GENERAL_FLAGS2:
        if hasattr(obj.composite_flags2, f):
            setattr(obj.composite_flags2, f, True)


def _new_empty(name, sollum_type, collection, parent=None):
    o = bpy.data.objects.new(name, None)
    o.empty_display_size = 0
    o.sollum_type = sollum_type
    collection.objects.link(o)
    if parent:
        o.parent = parent
    return o


def _delete_hierarchy(obj):
    objs = [obj] + list(obj.children_recursive)
    meshes = {o.data for o in objs if o.type == "MESH"}
    for o in objs:
        bpy.data.objects.remove(o, do_unlink=True)
    for m in meshes:
        if m.users == 0:
            bpy.data.meshes.remove(m)


def build_drawable(context, s):
    name = s.name.strip() or "prop_custom_ladder"
    coll = context.collection

    if s.replace_existing and name in bpy.data.objects:
        _delete_hierarchy(bpy.data.objects[name])

    # Drawable
    drawable = _new_empty(name, SZ_DRAWABLE, coll)
    drawable.location = context.scene.cursor.location.copy()

    # Model (visuel)
    vis_mesh = build_visual_mesh(s, f"{name}.model")
    model = bpy.data.objects.new(f"{name}.model", vis_mesh)
    coll.objects.link(model)
    model.parent = drawable
    model.sollum_type = SZ_DRAWABLE_MODEL
    lods_mod = _sz("sollumz_properties")
    model.sz_lods.get_lod(lods_mod.LODLevel.HIGH).mesh = vis_mesh
    model.sz_lods.active_lod_level = lods_mod.LODLevel.HIGH
    create_ladder_material(s, name, model)

    # Collision embarquée
    composite = _new_empty(f"{name}.col", SZ_BOUND_COMPOSITE, coll, drawable)
    bvh = _new_empty(f"{name}.bvh", SZ_BOUND_BVH, coll, composite)
    _set_flags(bvh)
    col_mesh = build_collision_mesh(s, f"{name}.poly_mesh")
    col_mesh.materials.append(create_collision_material(s))
    poly = bpy.data.objects.new(f"{name}.poly_mesh", col_mesh)
    coll.objects.link(poly)
    poly.parent = bvh
    poly.sollum_type = SZ_BOUND_POLY_TRI

    return drawable


def ladder_extension_points(s):
    climber, half, rail_top, rungs = _ladder_layout(s)
    top = Vector((0.0, 0.0, s.height))
    bottom = Vector((0.0, 0.0, 0.0))
    normal = Vector((0.0, climber, 0.0))
    return top, bottom, normal


def _swap_mesh(obj, new_mesh):
    old = obj.data
    for m in old.materials:
        new_mesh.materials.append(m)
    obj.data = new_mesh
    if old.users == 0:
        bpy.data.meshes.remove(old)


def refresh_geometry(s, drawable):
    """Reconstruit le maillage visuel et la collision d'une échelle existante, sans toucher au reste."""
    name = drawable.name
    model = next((o for o in drawable.children_recursive if o.sollum_type == SZ_DRAWABLE_MODEL), None)
    poly = next((o for o in drawable.children_recursive if o.sollum_type == SZ_BOUND_POLY_TRI), None)

    if model is not None:
        new_mesh = build_visual_mesh(s, f"{name}.model")
        _swap_mesh(model, new_mesh)
        lods_mod = _sz("sollumz_properties")
        model.sz_lods.get_lod(lods_mod.LODLevel.HIGH).mesh = new_mesh
        if new_mesh.materials:
            _sz("ydr.operators.materials").post_create_shader_update_object(model, new_mesh.materials[0])

    if poly is not None:
        _swap_mesh(poly, build_collision_mesh(s, f"{name}.poly_mesh"))


def refresh_extensions(scene, s):
    top, bottom, normal = ladder_extension_points(s)
    n = 0
    for ytyp in scene.ytyps:
        for arch in ytyp.archetypes:
            if arch.name != s.name.strip():
                continue
            arch.lod_dist = s.lod_dist
            for ext in arch.extensions:
                if ext.extension_type == SZ_EXT_LADDER:
                    p = ext.ladder_extension_properties
                    p.top, p.bottom, p.normal = top, bottom, normal
                    p.offset_position = top
                    p.material_type = s.ladder_material
                    p.can_get_off_at_top = s.can_get_off_top
                    p.can_get_off_at_bottom = s.can_get_off_bottom
                    n += 1
    return n


def get_or_create_ytyp(context, s):
    scene = context.scene
    if s.ytyp_mode == "SELECTED":
        if len(scene.ytyps) == 0:
            raise RuntimeError(T("msg_no_ytyp"))
        return scene.ytyps[scene.ytyp_index]

    # NEW : réutilise un YTYP du même nom s'il existe
    for i, y in enumerate(scene.ytyps):
        if y.name == s.ytyp_name:
            scene.ytyp_index = i
            return y
    bpy.ops.sollumz.createytyp()
    ytyp = scene.ytyps[len(scene.ytyps) - 1]
    ytyp.name = s.ytyp_name
    scene.ytyp_index = len(scene.ytyps) - 1
    return ytyp


def build_archetype(context, s, drawable):
    ytyp = get_or_create_ytyp(context, s)
    name = drawable.name

    if s.replace_existing:
        for i in reversed(range(len(ytyp.archetypes))):
            if ytyp.archetypes[i].name == name:
                ytyp.archetypes.remove(i)

    arch = ytyp.new_archetype()
    arch.name = name
    arch.asset = drawable          # Sollumz déduit type DRAWABLE + physics dict (collision embarquée)
    arch.asset_name = name
    arch.texture_dictionary = name if s.embed_texture else ""
    arch.physics_dictionary = name
    arch.lod_dist = s.lod_dist

    ext = arch.new_extension(SZ_EXT_LADDER)
    ext.name = "Ladder"
    p = ext.ladder_extension_properties
    top, bottom, normal = ladder_extension_points(s)
    p.top = top
    p.bottom = bottom
    p.normal = normal
    p.offset_position = top
    p.material_type = s.ladder_material
    p.template = "default"
    p.can_get_off_at_top = s.can_get_off_top
    p.can_get_off_at_bottom = s.can_get_off_bottom
    return ytyp, arch


# --------------------------------------------------------------------------- #
#  Opérateurs
# --------------------------------------------------------------------------- #

class LADDER_OT_build(bpy.types.Operator):
    """Crée l'échelle : 3D + collision + YTYP / Create the ladder: 3D + collision + YTYP"""
    bl_idname = "ladderbuilder.build"
    bl_label = "Créer l'échelle"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.ladder_builder
        if _sollumz_package() is None:
            self.report({"ERROR"}, T("msg_no_sollumz"))
            return {"CANCELLED"}
        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        try:
            drawable = build_drawable(context, s)
            msg = T("msg_created", name=drawable.name)
            if s.ytyp_mode != "NONE":
                ytyp, arch = build_archetype(context, s, drawable)
                msg += T("msg_ytyp", ytyp=ytyp.name)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.report({"ERROR"}, T("msg_error", err=e))
            return {"CANCELLED"}

        for o in context.selected_objects:
            o.select_set(False)
        drawable.select_set(True)
        context.view_layer.objects.active = drawable
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class LADDER_OT_update_extension(bpy.types.Operator):
    """Reconstruit l'échelle existante (même nom) / Rebuild the existing ladder (same name)"""
    bl_idname = "ladderbuilder.update_extension"
    bl_label = "Mettre à jour l'échelle"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.ladder_builder
        drawable = bpy.data.objects.get(s.name.strip())
        if drawable is None:
            self.report({"WARNING"}, T("msg_not_found", name=s.name))
            return {"CANCELLED"}
        refresh_geometry(s, drawable)
        n = refresh_extensions(context.scene, s)
        self.report({"INFO"}, T("msg_updated", n=n))
        return {"FINISHED"}


# --------------------------------------------------------------------------- #
#  UI
# --------------------------------------------------------------------------- #

class LadderBuilderPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    language: EnumProperty(
        name="Langue / Language",
        items=[
            ("AUTO", "Auto (Blender)", "Suit la langue de Blender / Follows Blender's language"),
            ("FR", "Français", ""),
            ("EN", "English", ""),
        ],
        default="AUTO",
    )

    def draw(self, context):
        self.layout.prop(self, "language")


def _prefs(context):
    addon = context.preferences.addons.get(__package__)
    return addon.preferences if addon else None


SOLLUMZ_CATEGORY = "Sollumz Tools"


class LADDER_PT_panel(bpy.types.Panel):
    bl_label = "Byfred Ladder Builder"
    bl_idname = "LADDER_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = SOLLUMZ_CATEGORY
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 100

    def draw_header(self, context):
        self.layout.label(text="", icon="SORTSIZE")

    def draw(self, context):
        s = context.scene.ladder_builder
        layout = self.layout

        prefs = _prefs(context)
        if prefs is not None:
            row = layout.row(align=True)
            row.prop(prefs, "language", text=T("language"), expand=True)

        if _sollumz_package() is None:
            layout.label(text=T("no_sollumz"), icon="ERROR")

        layout.prop(s, "name", text=T("name"))
        layout.prop(s, "live_update", text=T("live"), icon="REC" if s.live_update else "PAUSE", toggle=True)
        if s.live_update and bpy.data.objects.get(s.name.strip()) is None:
            layout.label(text=T("live_hint"), icon="INFO")
        layout.prop(s, "replace_existing", text=T("replace"))

        col = layout.column(align=True)
        col.scale_y = 1.3
        col.operator(LADDER_OT_build.bl_idname, text=T("build"), icon="ADD")
        layout.operator(LADDER_OT_update_extension.bl_idname, text=T("refresh"), icon="FILE_REFRESH")


class _LadderChildPanel:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = SOLLUMZ_CATEGORY
    bl_parent_id = LADDER_PT_panel.bl_idname
    bl_options = {"DEFAULT_CLOSED"}
    _title_key = ""
    _icon = "NONE"

    def draw_header(self, context):
        self.layout.label(text=T(self._title_key), icon=self._icon)


class LADDER_PT_dimensions(_LadderChildPanel, bpy.types.Panel):
    bl_label = ""
    bl_idname = "LADDER_PT_dimensions"
    bl_options = set()
    bl_order = 0
    _title_key = "sec_dims"
    _icon = "MOD_LENGTH"

    def draw(self, context):
        s = context.scene.ladder_builder
        col = self.layout.column(align=True)
        for key in ("height", "top_extension", "width", "rung_spacing", "first_rung"):
            col.prop(s, key, text=T(key))
        self.layout.prop(s, "rungs_to_top", text=T("rungs_to_top"))


class LADDER_PT_profile(_LadderChildPanel, bpy.types.Panel):
    bl_label = ""
    bl_idname = "LADDER_PT_profile"
    bl_order = 1
    _title_key = "sec_profile"
    _icon = "MESH_CYLINDER"

    def draw(self, context):
        s = context.scene.ladder_builder
        layout = self.layout
        layout.row().prop(s, "profile", expand=True)
        col = layout.column(align=True)
        col.prop(s, "rail_size", text=T("rail_size"))
        col.prop(s, "rung_size", text=T("rung_size"))
        if s.profile == "ROUND":
            col.prop(s, "segments", text=T("segments"))


class LADDER_PT_accessories(_LadderChildPanel, bpy.types.Panel):
    bl_label = ""
    bl_idname = "LADDER_PT_accessories"
    bl_order = 2
    _title_key = "sec_access"
    _icon = "MODIFIER"

    def draw(self, context):
        s = context.scene.ladder_builder
        layout = self.layout
        layout.prop(s, "access_side", text=T("access_side"))
        row = layout.row()
        row.prop(s, "wall_brackets", text=T("wall_brackets"))
        sub = row.row()
        sub.enabled = s.wall_brackets
        sub.prop(s, "wall_offset", text=T("wall_offset"))
        layout.prop(s, "cage", text=T("cage"))
        if s.cage:
            col = layout.column(align=True)
            col.prop(s, "cage_start", text=T("cage_start"))
            col.prop(s, "cage_radius", text=T("cage_radius"))
            col.prop(s, "cage_spacing", text=T("cage_spacing"))


class LADDER_PT_materials(_LadderChildPanel, bpy.types.Panel):
    bl_label = ""
    bl_idname = "LADDER_PT_materials"
    bl_order = 3
    _title_key = "sec_mat"
    _icon = "MATERIAL"

    def draw(self, context):
        s = context.scene.ladder_builder
        layout = self.layout
        layout.prop(s, "color", text=T("color"))
        layout.prop(s, "embed_texture", text=T("embed_texture"))
        layout.prop(s, "collision_material", text=T("collision_material"))
        if s.live_update:
            layout.label(text=T("mat_not_live"), icon="INFO")


class LADDER_PT_ytyp(_LadderChildPanel, bpy.types.Panel):
    bl_label = ""
    bl_idname = "LADDER_PT_ytyp"
    bl_order = 4
    _title_key = "sec_ytyp"
    _icon = "OBJECT_DATA"

    def draw(self, context):
        s = context.scene.ladder_builder
        layout = self.layout
        layout.prop(s, "ytyp_mode", text="")
        if s.ytyp_mode == "NEW":
            layout.prop(s, "ytyp_name", text=T("ytyp_name"))
        if s.ytyp_mode != "NONE":
            layout.prop(s, "ladder_material", text=T("ladder_material"))
            row = layout.row()
            row.prop(s, "can_get_off_top", text=T("can_get_off_top"))
            row.prop(s, "can_get_off_bottom", text=T("can_get_off_bottom"))
            layout.prop(s, "lod_dist", text=T("lod_dist"))


classes = (
    LadderBuilderPreferences,
    LadderBuilderSettings,
    LADDER_OT_build,
    LADDER_OT_update_extension,
    LADDER_PT_panel,
    LADDER_PT_dimensions,
    LADDER_PT_profile,
    LADDER_PT_accessories,
    LADDER_PT_materials,
    LADDER_PT_ytyp,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.ladder_builder = PointerProperty(type=LadderBuilderSettings)


def unregister():
    del bpy.types.Scene.ladder_builder
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
