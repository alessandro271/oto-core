"""AI search visibility: brand mentions in AI answers, model responses, Google AI Mode.

`targets` for the LLM-mentions endpoints is DataForSEO's list of target entities
(up to 10), each `{"domain": "example.com"}` or `{"keyword": "crm"}`, with
optional `search_filter` (`include`|`exclude`), `search_scope` (e.g.
`["answer"]`) and `match_type`. `platform`: `google` (AI Overviews) or
`chat_gpt` (United States, English only); none = both.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

_MENTIONS = "/ai_optimization/llm_mentions"
LLM_ENGINES = ("chat_gpt", "claude", "gemini", "perplexity")


class AiMixin:

    def _mentions(self, endpoint: str, targets: List[Dict[str, Any]], platform, loc,
                  extra: Dict[str, Any]) -> Dict[str, Any]:
        task = self._location({"target": targets, "platform": platform, **extra}, *loc)
        return self._live(f"{_MENTIONS}/{endpoint}/live", task)

    def llm_mentions_search(
        self, targets: List[Dict[str, Any]], platform: Optional[str] = None,
        location_code: Optional[int] = None, location_name: Optional[str] = None,
        language_code: Optional[str] = None, language_name: Optional[str] = None,
        limit: Optional[int] = None, offset: Optional[int] = None,
        filters: Optional[list] = None, order_by: Optional[List[str]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST /ai_optimization/llm_mentions/search_mentions/live — the AI answers
        (question, answer, sources) that mention the targets. API default limit
        100, max 1000."""
        return self._mentions("search_mentions", targets, platform,
                              (location_code, location_name, language_code, language_name),
                              {"limit": limit, "offset": offset, "filters": filters,
                               "order_by": order_by, **(options or {})})

    def llm_mentions_metrics(
        self, targets: List[Dict[str, Any]], platform: Optional[str] = None,
        location_code: Optional[int] = None, location_name: Optional[str] = None,
        language_code: Optional[str] = None, language_name: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST /ai_optimization/llm_mentions/target_metrics/live — mention count,
        AI search volume and impressions for the targets, by platform and source."""
        return self._mentions("target_metrics", targets, platform,
                              (location_code, location_name, language_code, language_name),
                              dict(options or {}))

    def llm_mentions_top_domains(
        self, targets: List[Dict[str, Any]], platform: Optional[str] = None,
        location_code: Optional[int] = None, location_name: Optional[str] = None,
        language_code: Optional[str] = None, language_name: Optional[str] = None,
        limit: Optional[int] = None, options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST /ai_optimization/llm_mentions/top_mentioned_domains/live — the
        domains AI answers cite most for the targets."""
        return self._mentions("top_mentioned_domains", targets, platform,
                              (location_code, location_name, language_code, language_name),
                              {"limit": limit, **(options or {})})

    def llm_mentions_top_pages(
        self, targets: List[Dict[str, Any]], platform: Optional[str] = None,
        location_code: Optional[int] = None, location_name: Optional[str] = None,
        language_code: Optional[str] = None, language_name: Optional[str] = None,
        limit: Optional[int] = None, options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST /ai_optimization/llm_mentions/top_mentioned_pages/live — the pages
        AI answers cite most for the targets."""
        return self._mentions("top_mentioned_pages", targets, platform,
                              (location_code, location_name, language_code, language_name),
                              {"limit": limit, **(options or {})})

    def llm_mentions_history(
        self, targets: List[Dict[str, Any]], platform: Optional[str] = None,
        location_code: Optional[int] = None, location_name: Optional[str] = None,
        language_code: Optional[str] = None, language_name: Optional[str] = None,
        date_from: Optional[str] = None, date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /ai_optimization/llm_mentions/historical/live — mention metrics per
        month (data from 2025-08-01). Dates `yyyy-mm-dd`."""
        return self._mentions("historical", targets, platform,
                              (location_code, location_name, language_code, language_name),
                              {"date_from": date_from, "date_to": date_to})

    def llm_response(
        self, engine: str, user_prompt: str, model_name: str,
        web_search: Optional[bool] = None, web_search_country_iso_code: Optional[str] = None,
        max_output_tokens: Optional[int] = None, options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST /ai_optimization/{engine}/llm_responses/live — ask a model a
        question and get its answer with the sources it cites. `engine`: one of
        `LLM_ENGINES`; `model_name` from `llm_models(engine)`. Billed on the
        model's tokens plus DataForSEO's fee."""
        if engine not in LLM_ENGINES:
            raise ValueError(f"engine must be one of {', '.join(LLM_ENGINES)}")
        return self._live(f"/ai_optimization/{engine}/llm_responses/live", {
            "user_prompt": user_prompt, "model_name": model_name, "web_search": web_search,
            "web_search_country_iso_code": web_search_country_iso_code,
            "max_output_tokens": max_output_tokens, **(options or {})})

    def llm_models(self, engine: str) -> Dict[str, Any]:
        """GET /ai_optimization/{engine}/llm_responses/models — the model names
        `llm_response` accepts. Free."""
        if engine not in LLM_ENGINES:
            raise ValueError(f"engine must be one of {', '.join(LLM_ENGINES)}")
        return self._task("GET", f"/ai_optimization/{engine}/llm_responses/models")

    def google_ai_mode(
        self, keyword: str, location_code: Optional[int] = None,
        location_name: Optional[str] = None, language_code: Optional[str] = None,
        language_name: Optional[str] = None, device: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST /serp/google/ai_mode/live/advanced — Google's AI Mode answer for a
        query, with the sources it cites. Location and language required."""
        task = self._location({"keyword": keyword, "device": device}, location_code,
                              location_name, language_code, language_name)
        return self._live("/serp/google/ai_mode/live/advanced", {**task, **(options or {})})

    def ai_keyword_search_volume(
        self, keywords: List[str], location_code: Optional[int] = None,
        location_name: Optional[str] = None, language_code: Optional[str] = None,
        language_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /ai_optimization/ai_keyword_data/keywords_search_volume/live — how
        often each keyword is asked to AI assistants, with a monthly trend (max
        1000). Location and language required."""
        task = self._location({"keywords": keywords}, location_code, location_name,
                              language_code, language_name)
        return self._live("/ai_optimization/ai_keyword_data/keywords_search_volume/live", task)
