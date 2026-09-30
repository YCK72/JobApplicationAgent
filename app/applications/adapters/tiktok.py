from __future__ import annotations

from app.applications.adapters.greenhouse import GreenhouseFormAdapter


class TikTokFormAdapter(GreenhouseFormAdapter):
    """Inspect native controls on an official TikTok application page.

    The shared inspector reads native form controls only and does not bypass
    login, verification, or submission boundaries.
    """

    @property
    def provider_name(self) -> str:
        return "TIKTOK"
