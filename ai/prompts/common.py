# ai/prompts/common.py
"""Shared retry instruction for section extraction prompts."""

RETRY_TEMPLATE = """Önceki JSON yanıtın şema doğrulamasından geçmedi:
{error}

Aynı sayfaları yeniden incele ve yalnızca şemaya uyan DÜZELTİLMİŞ JSON nesnesini döndür.
Markdown kod bloğu veya açıklama ekleme. Okunamayan metni tahmin etme; UNREADABLE yaz."""
