"""Traductions Français / English pour Byfred Ladder Builder."""

import bpy

# clé -> (français, english)
TEXTS = {
    # Général
    "panel": ("Byfred Ladder Builder", "Byfred Ladder Builder"),
    "language": ("Langue", "Language"),
    "no_sollumz": ("Sollumz n'est pas activé !", "Sollumz is not enabled!"),
    "name": ("Nom", "Name"),
    "live": ("Temps réel", "Live update"),
    "live_hint": ("Crée l'échelle pour activer le temps réel", "Create the ladder to enable live update"),
    "replace": ("Remplacer si existe", "Replace if exists"),
    "build": ("Créer l'échelle", "Create ladder"),
    "refresh": ("Mettre à jour l'échelle", "Update ladder"),

    # Sections
    "sec_dims": ("Dimensions", "Dimensions"),
    "sec_profile": ("Profil", "Profile"),
    "sec_access": ("Accessoires", "Accessories"),
    "sec_mat": ("Matériaux", "Materials"),
    "sec_ytyp": ("YTYP / Extension Ladder", "YTYP / Ladder extension"),

    # Dimensions
    "height": ("Hauteur à grimper", "Climb height"),
    "top_extension": ("Dépassement haut", "Top extension"),
    "width": ("Largeur", "Width"),
    "rung_spacing": ("Espacement barreaux", "Rung spacing"),
    "rungs_to_top": ("Barreaux jusqu'en haut", "Rungs up to the top"),
    "first_rung": ("1er barreau", "First rung"),

    # Profil
    "rail_size": ("Épaisseur montant", "Rail thickness"),
    "rung_size": ("Épaisseur barreau", "Rung thickness"),
    "segments": ("Segments (rond)", "Segments (round)"),

    # Accessoires
    "access_side": ("Côté grimpeur", "Climber side"),
    "wall_brackets": ("Fixations murales", "Wall brackets"),
    "wall_offset": ("Mur", "Wall"),
    "cage": ("Crinoline (cage)", "Safety cage"),
    "cage_start": ("Début cage", "Cage start"),
    "cage_radius": ("Rayon cage", "Cage radius"),
    "cage_spacing": ("Espacement arceaux", "Hoop spacing"),

    # Matériaux
    "color": ("Couleur", "Color"),
    "embed_texture": ("Texture intégrée (DDS)", "Embedded texture (DDS)"),
    "collision_material": ("Matériau collision", "Collision material"),
    "mat_not_live": ("Couleur / collision : recliquer « Créer »", "Color / collision: click “Create” again"),

    # YTYP
    "ytyp_name": ("Nom YTYP", "YTYP name"),
    "ladder_material": ("Type échelle", "Ladder type"),
    "can_get_off_top": ("Sortie en haut", "Get off at top"),
    "can_get_off_bottom": ("Sortie en bas", "Get off at bottom"),
    "lod_dist": ("Distance LOD", "LOD distance"),

    # Messages
    "msg_no_sollumz": ("Sollumz n'est pas activé.", "Sollumz is not enabled."),
    "msg_created": ("Échelle '{name}' créée", "Ladder '{name}' created"),
    "msg_ytyp": (" + archetype dans le YTYP '{ytyp}'", " + archetype in YTYP '{ytyp}'"),
    "msg_error": ("Erreur : {err}", "Error: {err}"),
    "msg_not_found": ("Aucune échelle nommée '{name}' : clique d'abord sur « Créer l'échelle »",
                      "No ladder named '{name}': click “Create ladder” first"),
    "msg_updated": ("Échelle mise à jour ({n} extension(s) Ladder)", "Ladder updated ({n} Ladder extension(s))"),
    "msg_no_ytyp": ("Aucun YTYP dans la scène : choisis « Créer un nouveau YTYP ».",
                    "No YTYP in the scene: choose “Create a new YTYP”."),
}

# Listes déroulantes : identifiant -> ((fr, en), ...)
ENUMS = {
    "profile": (
        ("ROUND", ("Rond (tube)", "Round (tube)")),
        ("SQUARE", ("Carré", "Square")),
    ),
    "access_side": (
        ("NEG_Y", ("-Y (face vue avant)", "-Y (front view side)")),
        ("POS_Y", ("+Y", "+Y")),
    ),
    "collision_material": (
        ("METAL_SOLID_MEDIUM", ("Métal plein (moyen)", "Metal solid (medium)")),
        ("METAL_SOLID_SMALL", ("Métal plein (petit)", "Metal solid (small)")),
        ("METAL_HOLLOW_MEDIUM", ("Métal creux (moyen)", "Metal hollow (medium)")),
        ("METAL_RAILING", ("Rambarde métal", "Metal railing")),
        ("WOOD_SOLID_MEDIUM", ("Bois plein (moyen)", "Wood solid (medium)")),
        ("WOOD_SOLID_SMALL", ("Bois plein (petit)", "Wood solid (small)")),
    ),
    "ladder_material": (
        ("METAL_SOLID_LADDER", ("Métal (METAL_SOLID_LADDER)", "Metal (METAL_SOLID_LADDER)")),
        ("METAL_LIGHT_LADDER", ("Métal léger (METAL_LIGHT_LADDER)", "Light metal (METAL_LIGHT_LADDER)")),
        ("WOOD_LADDER", ("Bois (WOOD_LADDER)", "Wood (WOOD_LADDER)")),
    ),
    "ytyp_mode": (
        ("NEW", ("Créer un nouveau YTYP", "Create a new YTYP")),
        ("SELECTED", ("Ajouter au YTYP sélectionné", "Add to selected YTYP")),
        ("NONE", ("Pas de YTYP", "No YTYP")),
    ),
}

_ADDON_ID = __package__


def get_language() -> str:
    """'FR' ou 'EN' selon les préférences de l'addon (AUTO = langue de Blender)."""
    lang = "AUTO"
    try:
        lang = bpy.context.preferences.addons[_ADDON_ID].preferences.language
    except (KeyError, AttributeError):
        pass
    if lang == "AUTO":
        try:
            locale = bpy.app.translations.locale or ""
        except Exception:
            locale = ""
        return "FR" if locale.lower().startswith("fr") else "EN"
    return lang


def T(key: str, **fmt) -> str:
    pair = TEXTS.get(key)
    if pair is None:
        return key
    text = pair[0] if get_language() == "FR" else pair[1]
    return text.format(**fmt) if fmt else text


# Blender exige que les chaînes des enums dynamiques restent référencées : on les met en cache.
_ENUM_CACHE = {}


def enum_items(enum_key: str):
    def _items(self, context):
        lang = get_language()
        cache_key = (enum_key, lang)
        items = _ENUM_CACHE.get(cache_key)
        if items is None:
            idx = 0 if lang == "FR" else 1
            items = [(ident, labels[idx], "", i) for i, (ident, labels) in enumerate(ENUMS[enum_key])]
            _ENUM_CACHE[cache_key] = items
        return items
    return _items


def enum_ids(enum_key: str):
    return [ident for ident, _ in ENUMS[enum_key]]
