"""Reusable VRM export helper for the rigged-avatars track (WI 925).

Takes an existing **bone-parented** armature (no skinning required — the saturday06 VRM add-on exports
object-parented rigid meshes as valid VRM), maps its bones to VRM humanoid slots, sets clean-lane meta,
declares one spring-bone chain, and exports **VRM 1.0** (master) + **VRM 0.x** (derived, for VSeeFace).

Requires the saturday06 VRM add-on (Blender 4.2+). On ai2 that is `~/blender-4.2/blender` (WI 933) — the
system `/usr/bin/blender` 4.0.2 does NOT have it. Import this from a generator (e.g. blender_corn.py)
behind a `--vrm` flag.

Extended, never forked, by each work item that needed more of the format: WI 926 added skinning and the
ARKit expression binds, WI 936 drove the 52-name contract through it unchanged, WI 938 reused it verbatim for
a second archetype, and WI 1362 added fractional bind weights, the optional eye humanoid slots, bone-driven
gaze and the opt-in scene purge. New behaviour is opt-in so earlier callers keep their exact prior output.

The add-on API property paths here were read from a live introspection probe on ai2 (v4.4.0), not memory.
"""
import bpy
import addon_utils

VRM_ADDON = "bl_ext.user_default.vrm"

# our bone name -> (VRM 1.0 humanoid slot attribute, VRM 0.0 bone-name string)
HUMANOID_19 = {
    "hips": ("hips", "hips"), "spine": ("spine", "spine"), "chest": ("chest", "chest"),
    "neck": ("neck", "neck"), "head": ("head", "head"),
    "shoulder.L": ("left_shoulder", "leftShoulder"), "upper_arm.L": ("left_upper_arm", "leftUpperArm"),
    "forearm.L": ("left_lower_arm", "leftLowerArm"), "hand.L": ("left_hand", "leftHand"),
    "shoulder.R": ("right_shoulder", "rightShoulder"), "upper_arm.R": ("right_upper_arm", "rightUpperArm"),
    "forearm.R": ("right_lower_arm", "rightLowerArm"), "hand.R": ("right_hand", "rightHand"),
    "thigh.L": ("left_upper_leg", "leftUpperLeg"), "shin.L": ("left_lower_leg", "leftLowerLeg"),
    "foot.L": ("left_foot", "leftFoot"),
    "thigh.R": ("right_upper_leg", "rightUpperLeg"), "shin.R": ("right_lower_leg", "rightLowerLeg"),
    "foot.R": ("right_foot", "rightFoot"),
}
# Same map plus the two OPTIONAL eye slots (WI 1362). Eye bones make gaze bone-driven, which turns the
# eight `eyeLook*` ARKit clips into legitimate free stubs; `left_eye`/`right_eye` are not in REQUIRED_VRM1,
# so binding them does not tighten the required-slot check.
HUMANOID_19_EYES = dict(HUMANOID_19, **{
    "eye.L": ("left_eye", "leftEye"),
    "eye.R": ("right_eye", "rightEye"),
})

# VRM 1.0's 15 required humanoid slots (for validation)
REQUIRED_VRM1 = {"hips", "spine", "head", "left_upper_arm", "left_lower_arm", "left_hand",
                 "right_upper_arm", "right_lower_arm", "right_hand", "left_upper_leg", "left_lower_leg",
                 "left_foot", "right_upper_leg", "right_lower_leg", "right_foot"}


def ensure_addon():
    """The VRM add-on registers Armature.vrm_addon_extension; a prior read_factory_settings() (as
    blender_corn.py calls) disables it AND drops its add-on preferences (which the VRM validator
    requires), so re-enable with default_set=True to recreate both before touching VRM data."""
    if VRM_ADDON not in bpy.context.preferences.addons:
        addon_utils.enable(VRM_ADDON, default_set=True, persistent=True)
    if not hasattr(bpy.types.Armature, "vrm_addon_extension") or VRM_ADDON not in bpy.context.preferences.addons:
        raise SystemExit("VRM add-on not available — run under a Blender 4.2+ with the saturday06 VRM "
                         "add-on installed (on ai2: ~/blender-4.2/blender, not /usr/bin/blender).")


def _set_humanoid(ext, bones, humanoid):
    present = {b.name for b in bones}
    hb1 = ext.vrm1.humanoid.human_bones
    for our, (slot1, name0) in humanoid.items():
        if our not in present:
            raise SystemExit(f"humanoid map references missing bone {our!r}")
        getattr(hb1, slot1).node.bone_name = our
    missing = REQUIRED_VRM1 - {humanoid[o][0] for o in humanoid}
    if missing:
        raise SystemExit(f"humanoid map does not cover required VRM1 slots: {sorted(missing)}")
    # VRM 0.x humanoid is a collection of {bone: <vrm0 name>, node.bone_name: <our bone>}
    h0 = ext.vrm0.humanoid.human_bones
    h0.clear()
    for our, (_slot1, name0) in humanoid.items():
        e = h0.add(); e.bone = name0; e.node.bone_name = our


def _set_meta(ext, name, author):
    m1 = ext.vrm1.meta
    m1.vrm_name = name
    m1.version = "1.0"
    m1.authors.clear(); a = m1.authors.add(); a.value = author
    m1.avatar_permission = "everyone"
    m1.commercial_usage = "corporation"
    m1.credit_notation = "unnecessary"
    m1.allow_redistribution = True          # clean-lane asset is freely redistributable (cf. 0.x CC0)
    m1.modification = "allowModificationRedistribution"
    m0 = ext.vrm0.meta
    m0.title = name
    m0.author = author
    m0.version = "1.0"
    m0.license_name = "CC0"
    m0.allowed_user_name = "Everyone"
    m0.violent_ussage_name = "Allow"
    m0.sexual_ussage_name = "Allow"
    m0.commercial_ussage_name = "Allow"


# VRM 1.0 preset expression attr -> VRM 0.x blend-shape preset_name enum (only the genuinely double-duty
# presets we compose; see WI 923 discovery: blink + visemes(aa/ih/ou/ee/oh) + emotions(happy/angry/sad/…)).
_VRM1_PRESET_TO_VRM0 = {
    "blink": "blink", "blink_left": "blink_l", "blink_right": "blink_r",
    "aa": "a", "ih": "i", "ou": "u", "ee": "e", "oh": "o",
    "happy": "joy", "angry": "angry", "sad": "sorrow", "relaxed": "fun", "neutral": "neutral",
    "look_up": "lookup", "look_down": "lookdown", "look_left": "lookleft", "look_right": "lookright",
}


def _bind(entry):
    """A bind entry is (mesh_object_name, shape_key_name) or (mesh, shape_key, weight).

    The 2-tuple form means weight 1.0, so every pre-WI-1362 caller (925/926/936/938) is unaffected.
    Fractional weights exist because a composed preset genuinely needs them — a viseme is a partial jaw
    plus a partial mouth shape, and the original hard-coded 1.0 could not express one (WI 1362)."""
    if len(entry) == 3:
        return entry[0], entry[1], float(entry[2])
    if len(entry) != 2:
        raise SystemExit(f"expression bind must be (mesh, shape_key[, weight]), got {entry!r}")
    mesh_name, sk_name = entry
    return mesh_name, sk_name, 1.0


def _set_expressions(ext, expr_spec):
    """Bind ARKit shape keys to VRM expressions on both specs (WI 926, extended by WI 1362).

    expr_spec = {
      "customs": {arkit_name: [bind, ...], ...},           # 1:1 raw ARKit morphs
      "presets": {vrm1_preset_attr: [bind, ...], ...},     # composed presets
      "overrides": {vrm1_preset_attr: {"override_mouth": "blend", ...}, ...},   # optional, WI 1362
    }
    where each `bind` is (mesh_object_name, shape_key_name[, weight]) — see _bind.

    Research rule (WI 923): raw ARKit shapes are 1:1 **custom** expressions ("one morph per clip"); the
    genuinely double-duty shapes are additionally composed into **presets** (blink, a viseme, an emotion).
    Binding both in one file is what answers the Warudo raw-morph-vs-expression precedence question. The
    bind selector `index` is the shape-key NAME string (probed live on v4.4.0), the mesh is by object name.

    Overrides ('none'|'block'|'blend', probed live on v4.4.0) stop stacked expressions from summing into a
    distorted face. They are applied to PRESETS only: a raw ARKit custom is the tracker's own channel and
    must not fight it."""
    v1 = ext.vrm1.expressions
    v1.custom.clear()
    for arkit_name, binds in expr_spec.get("customs", {}).items():
        ce = v1.custom.add(); ce.custom_name = arkit_name
        for entry in binds:
            mesh_name, sk_name, weight = _bind(entry)
            b = ce.morph_target_binds.add()
            b.node.mesh_object_name = mesh_name; b.index = sk_name; b.weight = weight
    for preset_attr, binds in expr_spec.get("presets", {}).items():
        pe = getattr(v1.preset, preset_attr)
        pe.morph_target_binds.clear()
        for entry in binds:
            mesh_name, sk_name, weight = _bind(entry)
            b = pe.morph_target_binds.add()
            b.node.mesh_object_name = mesh_name; b.index = sk_name; b.weight = weight
    for preset_attr, modes in expr_spec.get("overrides", {}).items():
        pe = getattr(v1.preset, preset_attr)
        for prop, value in modes.items():
            setattr(pe, prop, value)
    # VRM 0.x: presets only (0.x has no arbitrary custom ARKit clips; that is a 1.0 capability).
    bsm = ext.vrm0.blend_shape_master
    bsm.blend_shape_groups.clear()
    for preset_attr, binds in expr_spec.get("presets", {}).items():
        preset0 = _VRM1_PRESET_TO_VRM0.get(preset_attr)
        if preset0 is None:
            continue
        grp = bsm.blend_shape_groups.add(); grp.name = preset_attr; grp.preset_name = preset0
        for entry in binds:
            mesh_name, sk_name, weight = _bind(entry)
            bd = grp.binds.add()
            bd.mesh.mesh_object_name = mesh_name; bd.index = sk_name; bd.weight = weight


def _set_spring(ext, joint_bones, center_bone):
    """One VRM 1.0 spring chain over joint_bones, centred on center_bone (the `center` node is the
    anti-explosion tool from the WI 923 spring-bone finding — it keeps the chain from thrashing when the
    model translates). A head sphere collider is a deferred detail: raw-property colliders are skipped by
    the exporter (they need the add-on's `vrm.add_spring_bone1_collider` operator to back them with an
    Empty), and it adds little for an upward-pointing tuft — WI 925 follow-up."""
    sb = ext.spring_bone1
    sp = sb.springs.add(); sp.vrm_name = "tuft"
    sp.center.bone_name = center_bone
    for b in joint_bones:
        j = sp.joints.add(); j.node.bone_name = b
        j.hit_radius = 0.02; j.stiffness = 1.0; j.gravity_power = 0.1
        j.gravity_dir = (0.0, 0.0, -1.0); j.drag_force = 0.4


def _set_look_at_bone(ext, offset_from_head):
    """Bone-driven gaze (WI 1362). `type` accepts 'bone' | 'expression' (probed live on v4.4.0); bone mode
    is the discovery's preferred option — universally supported, trivially parametric, and it turns the
    eight `eyeLook*` ARKit clips into legitimate free stubs. `offset_from_head_bone` is the gaze origin
    relative to the head bone, in Blender's Z-up frame; the add-on converts it on export."""
    la = ext.vrm1.look_at
    la.type = "bone"
    la.offset_from_head_bone = tuple(offset_from_head)


def _purge_non_avatar(arm):
    """The VRM exporter is scene-global — unlike glTF it does not honour selection — so anything left in
    the scene rides along (WI 938 shipped a demo carrying Blender's startup `Cube`). Remove every object
    that is not the armature or one of its meshes. Opt-in: callers predating WI 1362 keep their exact
    prior output."""
    keep = {arm}
    for o in bpy.context.scene.objects:
        if o.type == 'MESH' and (o.parent is arm or any(
                getattr(md, "object", None) is arm for md in o.modifiers if md.type == 'ARMATURE')):
            keep.add(o)
    removed = [o.name for o in bpy.context.scene.objects if o not in keep]
    for o in list(bpy.context.scene.objects):
        if o not in keep:
            bpy.data.objects.remove(o, do_unlink=True)
    return removed


def export_vrm(arm, out_dir, name, author="asset-harness (WI 925)",
               humanoid=None, spring_joint_bones=(), center_bone="head", expressions=None,
               look_at_offset=None, purge_non_avatar=False):
    """Configure VRM data on `arm` and export {name}.vrm (1.0) + {name}.vrm0.vrm (0.x) into out_dir.
    `expressions` (WI 926) is the optional ARKit shape-key binding spec passed to _set_expressions.
    `look_at_offset` (WI 1362) switches gaze to bone mode with that head-relative offset.
    `purge_non_avatar` (WI 1362) removes non-avatar objects before the scene-global VRM export.
    Returns the two output paths."""
    from pathlib import Path
    ensure_addon()
    humanoid = humanoid or HUMANOID_19
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    ext = arm.data.vrm_addon_extension
    _set_humanoid(ext, arm.data.bones, humanoid)
    _set_meta(ext, name, author)
    if spring_joint_bones:
        _set_spring(ext, list(spring_joint_bones), center_bone)
    if expressions:
        _set_expressions(ext, expressions)
    if look_at_offset is not None:
        _set_look_at_bone(ext, look_at_offset)
    if purge_non_avatar:
        removed = _purge_non_avatar(arm)
        if removed:
            print(f"vrm_export: purged {len(removed)} non-avatar object(s) before export: {removed}")

    for o in bpy.context.scene.objects:
        o.select_set(False)
    arm.select_set(True); bpy.context.view_layer.objects.active = arm
    # Include the armature's mesh children (bone-parented rigid parts AND armature-modifier skinned meshes)
    # so a skinned probe (WI 926) is not dropped; the add-on gathers by armature_object_name, this is additive.
    for o in bpy.context.scene.objects:
        if o.type == 'MESH' and (o.parent is arm or any(
                getattr(md, "object", None) is arm for md in o.modifiers if md.type == 'ARMATURE')):
            o.select_set(True)

    # export_try_sparse_sk asks for sparse morph accessors, which would suit a face rig — a lid, a brow,
    # the lips all move a handful of vertices out of thousands. MEASURED on WI 1362: the VRM operator
    # accepts the flag and its output does not change. The glTF exporter does honour it (12,808 stored
    # morph elements against the VRM's 605,744 dense, plus normals). Kept as a statement of intent in
    # case a later add-on version honours it; do not expect a size win from it today.
    common = dict(armature_object_name=arm.name, ignore_warning=True, export_gltf_animations=False,
                  export_try_sparse_sk=True)
    p1 = out_dir / f"{name}.vrm"
    ext.spec_version = "1.0"
    bpy.ops.export_scene.vrm(filepath=str(p1), **common)
    p0 = out_dir / f"{name}.vrm0.vrm"
    ext.spec_version = "0.0"
    bpy.ops.export_scene.vrm(filepath=str(p0), **common)
    return p1, p0
