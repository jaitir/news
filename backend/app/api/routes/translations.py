from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.search import TranslationPreviewRequest, TranslationPreviewResponse
from app.services.translation_preview import (
    TranslationPreviewService,
    get_translation_preview_service,
)

router = APIRouter(prefix="/translations", tags=["translations"])


@router.post("/preview", response_model=TranslationPreviewResponse)
def preview_translation(
    payload: TranslationPreviewRequest,
    service: TranslationPreviewService = Depends(get_translation_preview_service),
) -> TranslationPreviewResponse:
    translated_text, detected_source, provider = service.translate_preview(
        text=payload.text,
        target_language=payload.target_language,
        source_language=payload.source_language,
    )
    return TranslationPreviewResponse(
        original_text=payload.text,
        translated_text=translated_text,
        source_language=detected_source,
        target_language=payload.target_language,
        provider=provider,
    )
