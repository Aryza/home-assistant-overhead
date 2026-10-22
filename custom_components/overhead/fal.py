"""Small fal REST adapter. No automatic retries of paid requests."""

import base64
import json
from urllib.parse import urlsplit
from .artwork import ArtworkError


def data_uri(raw):
    return "data:image/png;base64," + base64.b64encode(raw).decode()


class Fal:
    def __init__(self, key):
        self.key = key

    def generate(self, model, prompt, *, refs=(), aspect="4:3", retries=0):
        from .vendor import net, paint

        endpoint = (
            paint.T2I_ENDPOINT
            if model == "nano_banana_t2i"
            else paint.MODELS[model]["endpoint"]
        )
        body = {"prompt": prompt, "num_images": 1}
        if model == "flux_kontext":
            body.update(image_url=refs[0], aspect_ratio=aspect, output_format="png")
        elif model in ("seedream", "gpt_image"):
            body.update(
                image_urls=list(refs),
                image_size={"width": 1280, "height": 960}
                if model == "gpt_image"
                else {"width": 1536, "height": 1152},
            )
        else:
            body.update(aspect_ratio=aspect, output_format="png")
            if refs:
                body["image_urls"] = list(refs)
        raw, err = net.http(
            "https://fal.run/" + endpoint,
            self.key,
            auth_scheme="Key",
            body=json.dumps(body).encode(),
            timeout=120,
        )
        if err or not raw:
            raise ArtworkError("fal.ai submission did not complete")
        result = json.loads(raw)
        images = result.get("images") or (
            [result["image"]] if result.get("image") else []
        )
        if not images:
            raise ArtworkError("fal.ai returned no image")
        url = images[0]["url"]
        if url.startswith("data:image/"):
            return base64.b64decode(url.split(",", 1)[1], validate=True)
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or not (
                parsed.hostname == "fal.media"
                or parsed.hostname.endswith(".fal.media")
                or parsed.hostname.endswith(".fal.ai")
            )
        ):
            raise ArtworkError("Unexpected fal.ai image host")
        image, err = net.http(url, accept="image/*", timeout=60)
        if err or not image:
            raise ArtworkError("Generated image could not be downloaded")
        return image
