"""Save and load a TRELLIS.2 latent dict whole, so one latent can be decoded on two vendors.

Core SaveLatent keeps only `samples`; a TRELLIS.2 latent also carries `coords`, `coord_counts`,
`coord_resolution` and `model_frame`, which the shape decode reads. `torch.save` of the dict on
the CPU keeps them all. Spike scaffolding (WI 1613), not production.
"""
import os
import torch
import folder_paths


class SaveTrellisLatent:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"samples": ("LATENT",),
                             "filename_prefix": ("STRING", {"default": "wi1613/latent"})}}

    RETURN_TYPES = ()
    FUNCTION = "save"
    OUTPUT_NODE = True
    CATEGORY = "wi1613"

    def save(self, samples, filename_prefix):
        path = os.path.join(folder_paths.get_output_directory(), filename_prefix + ".pt")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        cpu = {k: (v.detach().cpu() if torch.is_tensor(v) else v) for k, v in samples.items()}
        torch.save(cpu, path)
        return {"ui": {"text": [path]}}


class LoadTrellisLatent:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"path": ("STRING", {"default": ""})}}

    RETURN_TYPES = ("LATENT",)
    FUNCTION = "load"
    CATEGORY = "wi1613"

    @classmethod
    def IS_CHANGED(cls, path):
        return os.path.getmtime(path) if os.path.exists(path) else float("nan")

    def load(self, path):
        return (torch.load(path, map_location="cpu", weights_only=False),)


NODE_CLASS_MAPPINGS = {"SaveTrellisLatent": SaveTrellisLatent, "LoadTrellisLatent": LoadTrellisLatent}
NODE_DISPLAY_NAME_MAPPINGS = {"SaveTrellisLatent": "Save TRELLIS latent (WI 1613)",
                              "LoadTrellisLatent": "Load TRELLIS latent (WI 1613)"}
