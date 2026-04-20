"use client";

import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  ApiError,
  exportSnapshotUrl,
  fetchHistory,
  fetchProviderStatuses,
  fetchReport,
  fetchSnapshot,
  fetchTranslationPreview,
  runSearch,
} from "@/lib/api";
import { COUNTRY_OPTIONS } from "@/lib/countries";
import type {
  ProviderStatus,
  SearchReport,
  SearchItem,
  SearchPayload,
  SearchResponse,
  SegmentReport,
  SourceProfile,
  SnapshotSummary,
} from "@/lib/types";

type Locale = "ru" | "en";

type SegmentTopicGroup = {
  topic: string;
  items: SearchItem[];
  summary: string;
  accents: string[];
  mentions: number;
  totalInSegment: number;
  sourceCount: number;
  countryCount: number;
  dominantEmotion: string;
  dominantStance: string;
};

type NarrativeSortMode = "signal" | "emotion";

const SOURCE_OPTIONS = [
  { id: "event_registry", label: { ru: "Event Registry", en: "Event Registry" } },
  { id: "gdelt", label: { ru: "GDELT", en: "GDELT" } },
  { id: "open_web", label: { ru: "Open Web", en: "Open Web" } },
  { id: "gnews", label: { ru: "GNews", en: "GNews" } },
  { id: "guardian", label: { ru: "Guardian", en: "Guardian" } },
  { id: "media_cloud", label: { ru: "Media Cloud", en: "Media Cloud" } },
  { id: "newsdata", label: { ru: "NewsData.io", en: "NewsData.io" } },
  { id: "x", label: { ru: "X", en: "X" } },
  { id: "telegram", label: { ru: "Telegram", en: "Telegram" } },
] as const;

const INITIAL_QUERY = "";

const SEARCH_PHASES = {
  ru: [
    "Подключение источников",
    "Сбор и очистка материалов",
    "Сравнение нарративов",
    "Сборка таблицы и сводки",
  ],
  en: [
    "Connecting providers",
    "Collecting and cleaning coverage",
    "Comparing narratives",
    "Building the table and summary",
  ],
} as const;

const COPY = {
  ru: {
    snapshotCreated: "Снимок",
    currentRead: "Текущий срез",
    results: "Материалы",
    rawHits: "Сырые попадания",
    countries: "Страны",
    languages: "Языки",
    narratives: "Нарративы",
    exportExcel: "Экспорт в Excel",
    exportExcelTooltip: "Экспорт в Excel",
    exportDocx: "Экспорт в DOCX",
    exportMenuTooltip: "Экспорт отчёта",
    openSnapshots: "Снимки",
    providerStatusesTitle: "Провайдеры",
    close: "Закрыть",
    closeModal: "Закрыть окно",
    providerHint: "Готовность провайдеров",
    hoverToInspect: "Наведи, чтобы посмотреть статусы",
    query: "Запрос",
    queryPlaceholder: "Например: США заключила договор с Китаем",
    lookback: "Дней",
    resultsPerSource: "Источники",
    countriesFilter: "Страны",
    sources: "Источники",
    selectedCountries: "Выбрано",
    allCountries: "Все страны",
    selectedSources: "Выбрано",
    allSources: "Все источники",
    runSearch: "Запустить поиск",
    runSearchTooltip: "Запустить поиск",
    sortByMood: "Сортировать по настроению",
    openNarrative: "Открыть материалы нарратива",
    narrativeMaterials: "Материалы нарратива",
    narrativeFocus: "Фокус нарратива",
    keyQuotesHint: "Показываем цитаты, которые лучше всего иллюстрируют темы и тон сегментов.",
    collapse: "Свернуть",
    expand: "Развернуть",
    runningSearch: "Идет поиск...",
    searchInProgress: "Идет поиск по источникам",
    errorPrefix: "Ошибка",
    providerReadiness: "Готовность провайдеров",
    readyShort: "готово",
    narrativesShort: "Нарративы",
    historyShort: "Снимки",
    clusters: "кластеров",
    items: "материалов",
    weightedSignal: "Вес сигнала",
    topSources: "Топ-источники",
    narrativesEmpty: "Нарративы появятся после первого успешного поиска.",
    historyEmpty: "Сохраненные снимки появятся после первого запуска.",
    loading: "загрузка",
    daysShort: "д",
    strategy: "Стратегия поиска",
    analysisMode: "Режим анализа",
    expandedQuery: "Расширенный запрос",
    anchorTerms: "Опорные термины",
    executiveSummary: "Сводка",
    mainNarratives: "Основные нарративы",
    crossMarketDifferences: "Различия по рынкам",
    notableDisputes: "Спорные линии",
    confidenceNotes: "Ограничения и уверенность",
    report: "Отчет",
    reportOverview: "Общая картина",
    segmentFocus: "Фокус сегмента",
    mainSegments: "Ключевые сегменты",
    detailLayer: "Подтипы",
    pendingLayer: "Требует разметки",
    segmentRole: "Роль сегмента",
    aggregateHint:
      "Это агрегирующий сегмент: в него входят оппозиционные, независимые и прозападные источники.",
    atomicHint:
      "Это отдельный подтип внутри негосударственного контура. Его материалы входят и в сводный сегмент.",
    registryCoverage: "Покрытие реестра",
    reportSegments: "Сегменты медиа",
    keyQuotes: "Ключевые цитаты",
    crossSegmentGaps: "Пробелы покрытия",
    uncoveredSources: "Не классифицированы",
    classifiedItems: "Классифицировано материалов",
    classifiedSources: "Классифицировано источников",
    totalSources: "Всего источников",
    totalItems: "Всего материалов",
    reportLoading: "Собираем структурированный отчет...",
    reportEmpty: "Отчет появится после первого успешного поиска.",
    reportFailed: "Не удалось собрать отчет. Попробуйте открыть снимок еще раз через несколько секунд.",
    topicMentions: "упоминаний",
    topicAccents: "Акценты",
    sourceExamples: "Примеры источников",
    sourceTypes: "Типы источников",
    countriesList: "Страны",
    complementarity: "Тон сегмента",
    omittedTopics: "Опущенные темы",
    topicCoverage: "Темы и материалы",
    materialsByTopic: "Все материалы темы",
    sourceCountShort: "источников",
    countryCountShort: "стран",
    openArticle: "Открыть статью",
    articleSummary: "AI резюме",
    quoteOrExcerpt: "Цитата / фрагмент",
    quoteSelection: "Как отобраны цитаты",
    quoteSelectionCopy:
      "Показываем самые весомые цитаты или фрагменты из сильных материалов. Короткие однословные цитаты и слабые обрывки отсеиваются.",
    labelTone: "Тон",
    labelStance: "Позиция",
    labelAlignment: "Совпадение с запросом",
    labelOriginality: "Тип публикации",
    labelTopic: "Тема",
    labelSourceType: "Тип источника",
    primarySegment: "Сегмент",
    sourceCoverageBySegment: "Покрытие по сегментам",
    countryCoverageBySegment: "Страны по сегментам",
    noSignal: "Пока без сигнала.",
    resultsTable: "Материалы",
    snapshotCreatedAt: "Создано",
    published: "Дата",
    source: "Источник",
    headline: "Заголовок",
    pivotSummary: "Саммари",
    narrative: "Нарратив",
    emotion: "Эмоция",
    stance: "Позиция",
    alignment: "Совпадение",
    originality: "Оригинальность",
    weight: "Вес",
    original: "Оригинал",
    curated: "проверенный источник",
    translationLoading: "Переводим...",
    translationUnavailable: "Перевод не получен",
    tableEmpty: "Таблица заполнится после первого успешного поиска.",
    unknown: "—",
  },
  en: {
    snapshotCreated: "Snapshot",
    currentRead: "Current read",
    results: "Results",
    rawHits: "Raw hits",
    countries: "Countries",
    languages: "Languages",
    narratives: "Narratives",
    exportExcel: "Export Excel",
    exportExcelTooltip: "Export to Excel",
    exportDocx: "Export to DOCX",
    exportMenuTooltip: "Export report",
    openSnapshots: "Snapshots",
    providerStatusesTitle: "Providers",
    close: "Close",
    closeModal: "Close dialog",
    providerHint: "Provider readiness",
    hoverToInspect: "Hover to inspect statuses",
    query: "Query",
    queryPlaceholder: "For example: The United States signed an agreement with China",
    lookback: "Days",
    resultsPerSource: "Sources",
    countriesFilter: "Countries",
    sources: "Sources",
    selectedCountries: "Selected",
    allCountries: "All countries",
    selectedSources: "Selected",
    allSources: "All sources",
    runSearch: "Run search",
    runSearchTooltip: "Run search",
    sortByMood: "Sort by mood",
    openNarrative: "Open narrative materials",
    narrativeMaterials: "Narrative materials",
    narrativeFocus: "Narrative focus",
    keyQuotesHint: "Showing the quotes that best illustrate themes and segment tone.",
    collapse: "Collapse",
    expand: "Expand",
    runningSearch: "Searching...",
    searchInProgress: "Search in progress",
    errorPrefix: "Error",
    providerReadiness: "Provider readiness",
    readyShort: "ready",
    narrativesShort: "Narratives",
    historyShort: "Snapshots",
    clusters: "clusters",
    items: "items",
    weightedSignal: "Weighted signal",
    topSources: "Top sources",
    narrativesEmpty: "Narratives will appear after the first successful search.",
    historyEmpty: "Saved snapshots will appear after the first run.",
    loading: "loading",
    daysShort: "d",
    strategy: "Search strategy",
    analysisMode: "Analysis mode",
    expandedQuery: "Expanded query",
    anchorTerms: "Anchor terms",
    executiveSummary: "Executive summary",
    mainNarratives: "Main narratives",
    crossMarketDifferences: "Cross-market differences",
    notableDisputes: "Disputed lines",
    confidenceNotes: "Confidence notes",
    report: "Report",
    reportOverview: "Overview",
    segmentFocus: "Segment focus",
    mainSegments: "Core segments",
    detailLayer: "Subtypes",
    pendingLayer: "Needs review",
    segmentRole: "Segment role",
    aggregateHint:
      "This is an aggregate segment combining opposition, independent, and western-aligned outlets.",
    atomicHint:
      "This is a specific subtype inside the non-state contour. Its materials are also counted in the aggregate segment.",
    registryCoverage: "Registry coverage",
    reportSegments: "Media segments",
    keyQuotes: "Key quotes",
    crossSegmentGaps: "Coverage gaps",
    uncoveredSources: "Unclassified",
    classifiedItems: "Classified items",
    classifiedSources: "Classified sources",
    totalSources: "Total sources",
    totalItems: "Total items",
    reportLoading: "Building structured report...",
    reportEmpty: "The report will appear after the first successful search.",
    reportFailed: "Failed to build the report. Try opening the snapshot again in a few seconds.",
    topicMentions: "mentions",
    topicAccents: "Accents",
    sourceExamples: "Source examples",
    sourceTypes: "Source types",
    countriesList: "Countries",
    complementarity: "Segment tone",
    omittedTopics: "Omitted topics",
    topicCoverage: "Topics and materials",
    materialsByTopic: "All items in topic",
    sourceCountShort: "sources",
    countryCountShort: "countries",
    openArticle: "Open article",
    articleSummary: "Article summary",
    quoteOrExcerpt: "Quote / excerpt",
    quoteSelection: "How quotes are selected",
    quoteSelectionCopy:
      "Shows the strongest quote or excerpt from high-weight items. One-word quotes and weak fragments are filtered out.",
    labelTone: "Tone",
    labelStance: "Stance",
    labelAlignment: "Query match",
    labelOriginality: "Publication type",
    labelTopic: "Topic",
    labelSourceType: "Source type",
    primarySegment: "Segment",
    sourceCoverageBySegment: "Coverage by segment",
    countryCoverageBySegment: "Countries by segment",
    noSignal: "No signal yet.",
    resultsTable: "Results",
    snapshotCreatedAt: "Created",
    published: "Published",
    source: "Source",
    headline: "Headline",
    pivotSummary: "Pivot summary",
    narrative: "Narrative",
    emotion: "Emotion",
    stance: "Stance",
    alignment: "Alignment",
    originality: "Originality",
    weight: "Weight",
    original: "Original",
    curated: "curated",
    translationLoading: "Translating...",
    translationUnavailable: "No translation",
    tableEmpty: "The table will populate after the first successful search.",
    unknown: "—",
  },
} as const;

const translationCache = new Map<string, string | null>();

function capitalizeFirst(value: string): string {
  if (!value) {
    return value;
  }
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function formatDate(value: string, locale: Locale): string {
  return new Intl.DateTimeFormat(locale === "ru" ? "ru-RU" : "en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatProviderName(provider: string): string {
  return provider.replaceAll("_", " ");
}

function formatStatus(status: string, locale: Locale): string {
  const map: Record<string, Record<Locale, string>> = {
    ok: { ru: "ok", en: "ok" },
    ready: { ru: "готов", en: "ready" },
    demo: { ru: "демо", en: "demo" },
    pending_setup: { ru: "настройка", en: "setup" },
    needs_key: { ru: "нужен ключ", en: "needs key" },
    needs_session: { ru: "нужна сессия", en: "needs session" },
    premium_required: { ru: "нужен premium", en: "premium required" },
    payment_required: { ru: "нужна оплата", en: "payment required" },
    paid_required: { ru: "нужен платный план", en: "paid plan" },
    invalid_request: { ru: "ошибка запроса", en: "invalid request" },
    limited_plan: { ru: "лимит плана", en: "limited plan" },
    unauthorized: { ru: "нет доступа", en: "unauthorized" },
    forbidden: { ru: "запрещено", en: "forbidden" },
    rate_limited: { ru: "лимит API", en: "rate limited" },
    quota_reached: { ru: "квота исчерпана", en: "quota reached" },
    error: { ru: "ошибка", en: "error" },
  };

  return map[status]?.[locale] ?? status.replaceAll("_", " ");
}

function formatEmotion(emotion: string, locale: Locale): string {
  const map: Record<string, Record<Locale, string>> = {
    positive: { ru: "позитив", en: "positive" },
    negative: { ru: "негатив", en: "negative" },
    neutral: { ru: "нейтрально", en: "neutral" },
  };
  return capitalizeFirst(map[emotion]?.[locale] ?? emotion);
}

function formatAlignment(alignment: string, locale: Locale): string {
  const map: Record<string, Record<Locale, string>> = {
    high: { ru: "высокое", en: "high" },
    medium: { ru: "среднее", en: "medium" },
    low: { ru: "низкое", en: "low" },
  };
  return capitalizeFirst(map[alignment]?.[locale] ?? alignment);
}

function formatStance(stance: string, locale: Locale): string {
  const map: Record<string, Record<Locale, string>> = {
    supports: { ru: "поддерживает", en: "supports" },
    disputes: { ru: "оспаривает", en: "disputes" },
    mixed: { ru: "смешанная", en: "mixed" },
    unclear: { ru: "неясно", en: "unclear" },
  };
  return capitalizeFirst(map[stance]?.[locale] ?? stance.replaceAll("_", " "));
}

function formatOriginality(originality: string, locale: Locale): string {
  const map: Record<string, Record<Locale, string>> = {
    original: { ru: "оригинал", en: "original" },
    syndicated: { ru: "перепечатка", en: "syndicated" },
    mixed: { ru: "смешано", en: "mixed" },
    unknown: { ru: "неизвестно", en: "unknown" },
  };
  return capitalizeFirst(map[originality]?.[locale] ?? originality.replaceAll("_", " "));
}

function formatAnalysisValue(value: string, locale: Locale): string {
  const map: Record<string, Record<Locale, string>> = {
    heuristic: { ru: "эвристика", en: "heuristic" },
    llm: { ru: "llm", en: "llm" },
    hybrid: { ru: "гибрид", en: "hybrid" },
  };
  return capitalizeFirst(map[value]?.[locale] ?? value.replaceAll("_", " "));
}

function formatSourceTypeLabel(value: string, locale: Locale): string {
  const map: Record<string, Record<Locale, string>> = {
    digital_media: { ru: "цифровые СМИ", en: "digital media" },
    telegram: { ru: "telegram", en: "telegram" },
    x: { ru: "x", en: "x" },
    news: { ru: "СМИ", en: "media" },
    social: { ru: "соцсети", en: "social" },
    wire: { ru: "агентство", en: "wire" },
    broadcaster: { ru: "вещатель", en: "broadcaster" },
  };
  return capitalizeFirst(map[value]?.[locale] ?? value.replaceAll("_", " "));
}

function formatSegmentLabel(value: string, locale: Locale): string {
  const normalized = value.trim().toLowerCase();
  const map: Record<string, Record<Locale, string>> = {
    state_aligned: { ru: "проправительственные", en: "state-aligned" },
    critical_non_state: {
      ru: "сводный контур: оппозиционные / независимые / прозападные",
      en: "aggregate: opposition / independent / western-aligned",
    },
    opposition: { ru: "оппозиционные", en: "opposition" },
    independent: { ru: "независимые", en: "independent" },
    western_aligned: { ru: "прозападные", en: "western-aligned" },
    unknown: { ru: "требует ручной разметки", en: "needs manual review" },
  };
  return capitalizeFirst(map[normalized]?.[locale] ?? value.replaceAll("_", " "));
}

function formatCountryLabel(value: string | null | undefined, locale: Locale): string {
  if (!value) {
    return locale === "ru" ? "—" : "—";
  }
  const normalized = value.trim().toLowerCase();
  const countryOption = COUNTRY_OPTIONS.find(
    (option) =>
      option.code.toLowerCase() === normalized || option.label.en.toLowerCase() === normalized,
  );
  if (countryOption) {
    return capitalizeFirst(countryOption.label[locale]);
  }
  const map: Record<string, Record<Locale, string>> = {
    ae: { ru: "ОАЭ", en: "UAE" },
    au: { ru: "Австралия", en: "Australia" },
    az: { ru: "Азербайджан", en: "Azerbaijan" },
    br: { ru: "Бразилия", en: "Brazil" },
    ca: { ru: "Канада", en: "Canada" },
    cn: { ru: "Китай", en: "China" },
    de: { ru: "Германия", en: "Germany" },
    eg: { ru: "Египет", en: "Egypt" },
    es: { ru: "Испания", en: "Spain" },
    fr: { ru: "Франция", en: "France" },
    gb: { ru: "Великобритания", en: "United Kingdom" },
    ge: { ru: "Грузия", en: "Georgia" },
    hk: { ru: "Гонконг", en: "Hong Kong" },
    id: { ru: "Индонезия", en: "Indonesia" },
    il: { ru: "Израиль", en: "Israel" },
    in: { ru: "Индия", en: "India" },
    ir: { ru: "Иран", en: "Iran" },
    jp: { ru: "Япония", en: "Japan" },
    kr: { ru: "Южная Корея", en: "South Korea" },
    lv: { ru: "Латвия", en: "Latvia" },
    my: { ru: "Малайзия", en: "Malaysia" },
    nl: { ru: "Нидерланды", en: "Netherlands" },
    ph: { ru: "Филиппины", en: "Philippines" },
    pk: { ru: "Пакистан", en: "Pakistan" },
    qa: { ru: "Катар", en: "Qatar" },
    ru: { ru: "Россия", en: "Russia" },
    sa: { ru: "Саудовская Аравия", en: "Saudi Arabia" },
    sg: { ru: "Сингапур", en: "Singapore" },
    sy: { ru: "Сирия", en: "Syria" },
    tr: { ru: "Турция", en: "Turkey" },
    us: { ru: "США", en: "United States" },
    usa: { ru: "США", en: "United States" },
    "united states": { ru: "США", en: "United States" },
    "united states of america": { ru: "США", en: "United States" },
    uk: { ru: "Великобритания", en: "United Kingdom" },
    "united kingdom": { ru: "Великобритания", en: "United Kingdom" },
    "great britain": { ru: "Великобритания", en: "United Kingdom" },
    ve: { ru: "Венесуэла", en: "Venezuela" },
    za: { ru: "ЮАР", en: "South Africa" },
    unknown: { ru: "не определено", en: "unknown" },
  };
  return capitalizeFirst(map[normalized]?.[locale] ?? value);
}

function formatComplementarity(value: string, locale: Locale): string {
  const map: Record<string, Record<Locale, string>> = {
    комплиментарная: { ru: "комплиментарная", en: "complimentary" },
    критическая: { ru: "критическая", en: "critical" },
    смешанная: { ru: "смешанная", en: "mixed" },
    нейтральная: { ru: "нейтральная", en: "neutral" },
    complimentary: { ru: "комплиментарная", en: "complimentary" },
    critical: { ru: "критическая", en: "critical" },
    mixed: { ru: "смешанная", en: "mixed" },
    neutral: { ru: "нейтральная", en: "neutral" },
  };
  return capitalizeFirst(map[value]?.[locale] ?? value);
}

function formatNarrativeLabel(value: string, locale: Locale): string {
  const normalized = value.trim().toLowerCase();
  const map: Record<string, Record<Locale, string>> = {
    "general framing": { ru: "основной контекст", en: "general framing" },
    diplomatic: { ru: "дипломатия", en: "diplomatic" },
    economic: { ru: "экономика", en: "economic" },
    security: { ru: "безопасность", en: "security" },
    governance: { ru: "госуправление", en: "governance" },
    "social reaction": { ru: "общественная реакция", en: "social reaction" },
    "u.s.-mexico policy dispute": { ru: "спор по политике США и Мексики", en: "u.s.-mexico policy dispute" },
    "markets and dollar": { ru: "рынки и доллар", en: "markets and dollar" },
    "tariff restoration": { ru: "восстановление пошлин", en: "tariff restoration" },
    "trade tariffs": { ru: "торговые пошлины", en: "trade tariffs" },
  };
  return capitalizeFirst(map[normalized]?.[locale] ?? value.replaceAll("_", " "));
}

function shouldOfferTranslation(text: string, locale: Locale, languageHint?: string | null): boolean {
  if (locale !== "ru") {
    return false;
  }
  if (languageHint?.toLowerCase().startsWith("ru")) {
    return false;
  }
  const hasForeignScript = /[A-Za-z\u0600-\u06FF\u4E00-\u9FFF]/.test(text);
  return hasForeignScript && text.trim().length >= 3;
}

function statusTone(status: string): string {
  if (status === "ready" || status === "ok") {
    return "bg-emerald-100 text-emerald-900";
  }
  if (status === "demo" || status === "pending_setup") {
    return "bg-amber-100 text-amber-900";
  }
  if (
    status === "needs_key" ||
    status === "needs_session" ||
    status === "premium_required" ||
    status === "payment_required" ||
    status === "paid_required" ||
    status === "invalid_request" ||
    status === "limited_plan" ||
    status === "unauthorized" ||
    status === "forbidden" ||
    status === "rate_limited" ||
    status === "quota_reached"
  ) {
    return "bg-amber-100 text-amber-900";
  }
  if (status === "error") {
    return "bg-rose-100 text-rose-900";
  }
  return "bg-slate-200 text-slate-700";
}

function emotionTone(emotion: string): string {
  if (emotion === "positive") {
    return "bg-emerald-200 text-emerald-900";
  }
  if (emotion === "negative") {
    return "bg-rose-200 text-rose-900";
  }
  return "bg-slate-200 text-slate-800";
}

function stanceTone(stance: string): string {
  if (stance === "supports") {
    return "bg-emerald-100 text-emerald-900";
  }
  if (stance === "disputes") {
    return "bg-rose-100 text-rose-900";
  }
  if (stance === "mixed") {
    return "bg-amber-100 text-amber-900";
  }
  return "bg-slate-200 text-slate-700";
}

function alignmentTone(alignment: string): string {
  if (alignment === "high") {
    return "bg-emerald-100 text-emerald-900";
  }
  if (alignment === "medium") {
    return "bg-amber-100 text-amber-900";
  }
  return "bg-slate-200 text-slate-700";
}

function originalityTone(originality: string): string {
  if (originality === "original") {
    return "bg-sky-100 text-sky-900";
  }
  if (originality === "syndicated") {
    return "bg-amber-100 text-amber-900";
  }
  if (originality === "mixed") {
    return "bg-violet-100 text-violet-900";
  }
  return "bg-slate-200 text-slate-700";
}

function complementarityTone(value: string): string {
  if (value === "комплиментарная" || value === "complimentary") {
    return "bg-emerald-100 text-emerald-900";
  }
  if (value === "критическая" || value === "critical") {
    return "bg-rose-100 text-rose-900";
  }
  if (value === "смешанная" || value === "mixed") {
    return "bg-amber-100 text-amber-900";
  }
  return "bg-slate-200 text-slate-800";
}

function countEntries(payload: Record<string, number | string[] | undefined>): number {
  return Object.keys(payload).length;
}

function sortedBreakdownEntries(payload: Record<string, number>): Array<[string, number]> {
  return Object.entries(payload).sort((left, right) => right[1] - left[1]);
}

function normalizeTopicKey(value: string): string {
  return value.trim().toLowerCase();
}

function extractSourceProfile(item: SearchItem): SourceProfile | null {
  return item.source_profile ?? null;
}

function segmentKind(segment: string): "aggregate" | "atomic" | "unknown" {
  if (segment === "critical_non_state") {
    return "aggregate";
  }
  if (segment === "unknown") {
    return "unknown";
  }
  return "atomic";
}

function itemBelongsToSegment(item: SearchItem, segment: string): boolean {
  const profile = extractSourceProfile(item);
  const primary = profile?.primary_segment ?? "unknown";
  const tags = new Set(profile?.segment_tags ?? []);

  if (segment === "critical_non_state") {
    return primary === "opposition" || primary === "independent" || primary === "western_aligned" || tags.has("critical_non_state");
  }
  if (segment === "unknown") {
    return primary === "unknown" || !profile;
  }
  return primary === segment;
}

function bestQuoteOrExcerpt(item: SearchItem, emphasis?: string): string | null {
  const candidates = [
    ...(item.exact_quotes ?? []),
    ...((item.summary || item.pivot_summary || item.title)
      .replace(/\s+/g, " ")
      .split(/[.!?]\s+/)
      .map((part) => part.trim())
      .filter((part) => part.length >= 24)),
  ];

  if (!candidates.length) {
    const fallback = item.summary || item.pivot_summary || item.title;
    return fallback.length ? fallback.slice(0, 220).trim() : null;
  }

  const anchorText = [
    item.title,
    item.pivot_summary,
    item.summary,
    item.cluster_label,
    item.narrative,
    emphasis,
  ]
    .join(" ")
    .toLowerCase();
  const anchorTokens = new Set(
    anchorText.match(/\b[\p{L}\p{N}-]{4,}\b/gu) ?? [],
  );
  const lowSignalPatterns = [
    "honored to host",
    "pleased to host",
    "honoured to host",
    "glad to welcome",
    "at india house today",
    "today,",
  ];

  const scored = candidates
    .map((candidate) => {
      const normalized = candidate.replace(/\s+/g, " ").trim();
      const candidateTokens = normalized.toLowerCase().match(/\b[\p{L}\p{N}-]{4,}\b/gu) ?? [];
      const overlap = candidateTokens.filter((token) => anchorTokens.has(token)).length;
      const hasDigits = /\d/.test(normalized);
      const lowSignalPenalty = lowSignalPatterns.some((pattern) => normalized.toLowerCase().includes(pattern)) ? 6 : 0;
      const score = overlap * 4 + (hasDigits ? 1 : 0) + Math.min(candidateTokens.length, 8) - lowSignalPenalty;
      return { candidate: normalized, score };
    })
    .sort((left, right) => right.score - left.score || right.candidate.length - left.candidate.length);

  return scored[0]?.candidate?.slice(0, 240).trim() ?? null;
}

function matchesNarrativeGroup(item: SearchItem, narrative: string, emotion: string): boolean {
  const label = item.cluster_label ?? item.narrative;
  return label === narrative && item.emotion === emotion;
}

function cleanCoverageGapText(value: string): string {
  return value.replace(/\*\*/g, "").replace(/\s+/g, " ").trim();
}

function pickDominantTone(counter: Record<string, number>, fallback: string): string {
  const entries = Object.entries(counter).sort((left, right) => right[1] - left[1]);
  return entries[0]?.[0] ?? fallback;
}

function summarizeTopic(items: SearchItem[]): string {
  const leader = [...items].sort((left, right) => right.weighted_score - left.weighted_score)[0];
  return leader?.pivot_summary || leader?.summary || leader?.title || "";
}

export function IntelDashboard() {
  const [locale, setLocale] = useState<Locale>("ru");
  const [query, setQuery] = useState(INITIAL_QUERY);
  const [lookbackDays, setLookbackDays] = useState(30);
  const [limitPerSource, setLimitPerSource] = useState(40);
  const [countriesFilter, setCountriesFilter] = useState<string[]>([]);
  const [sources, setSources] = useState<string[]>(
    SOURCE_OPTIONS.map((option) => option.id),
  );
  const [history, setHistory] = useState<SnapshotSummary[]>([]);
  const [providerStatuses, setProviderStatuses] = useState<ProviderStatus[]>([]);
  const [activeSearch, setActiveSearch] = useState<SearchResponse | null>(null);
  const [activeReport, setActiveReport] = useState<SearchReport | null>(null);
  const [selectedSegment, setSelectedSegment] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reportError, setReportError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isReportLoading, setIsReportLoading] = useState(false);
  const [searchPhaseIndex, setSearchPhaseIndex] = useState(0);
  const [loadingSnapshotId, setLoadingSnapshotId] = useState<string | null>(null);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [isProviderModalOpen, setIsProviderModalOpen] = useState(false);
  const [isNarrativesOpen, setIsNarrativesOpen] = useState(false);
  const [isQuotesOpen, setIsQuotesOpen] = useState(false);
  const [narrativeSortMode, setNarrativeSortMode] = useState<NarrativeSortMode>("signal");
  const [selectedNarrative, setSelectedNarrative] = useState<{ narrative: string; emotion: string } | null>(null);
  const reportRequestIdRef = useRef(0);
  const snapshotPollRequestIdRef = useRef(0);

  const t = COPY[locale];
  const iconButtonClass =
    "inline-flex h-[52px] w-[56px] items-center justify-center rounded-[18px] transition duration-200 hover:-translate-y-0.5 hover:shadow-[0_10px_24px_rgba(23,38,67,0.14)] disabled:cursor-not-allowed disabled:opacity-60";
  const isSearchProcessing = activeSearch?.snapshot.status === "processing";

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  useEffect(() => {
    if (!activeReport?.segment_reports.length) {
      setSelectedSegment(null);
      return;
    }

    const available = new Set(activeReport.segment_reports.map((segment) => segment.segment));
    if (!selectedSegment || !available.has(selectedSegment)) {
      setSelectedSegment(activeReport.segment_reports[0].segment);
    }
  }, [activeReport, selectedSegment]);

  useEffect(() => {
    if (!isSubmitting && !isSearchProcessing) {
      setSearchPhaseIndex(0);
      return;
    }

    const phases = SEARCH_PHASES[locale];
    const interval = window.setInterval(() => {
      setSearchPhaseIndex((current) => (current + 1) % phases.length);
    }, 1100);

    return () => window.clearInterval(interval);
  }, [isSearchProcessing, isSubmitting, locale]);

  useEffect(() => {
    setSelectedNarrative(null);
  }, [activeSearch?.snapshot.id]);

  const refreshHistory = useCallback(async () => {
    const historyResponse = await fetchHistory();
    setHistory(historyResponse.items);
  }, []);

  const hydrateFormFromSearch = useCallback((response: SearchResponse) => {
    setQuery(response.snapshot.query_text || "");
    setLookbackDays(response.snapshot.lookback_days || 30);
    setSources(
      response.snapshot.requested_sources?.length
        ? response.snapshot.requested_sources
        : SOURCE_OPTIONS.map((option) => option.id),
    );
    setCountriesFilter(response.snapshot.requested_countries ?? []);
  }, []);

  const wait = useCallback((ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms)), []);

  const loadReport = useCallback(async (snapshotId: string, retries = 8) => {
    const requestId = ++reportRequestIdRef.current;
    setIsReportLoading(true);
    setReportError(null);
    try {
      for (let attempt = 0; attempt < retries; attempt += 1) {
        try {
          const report = await fetchReport(snapshotId);
          if (reportRequestIdRef.current !== requestId) {
            return;
          }
          setActiveReport(report);
          setReportError(null);
          return;
        } catch (reportLoadError) {
          if (reportLoadError instanceof ApiError && reportLoadError.status === 409) {
            await new Promise((resolve) => window.setTimeout(resolve, 1500 + attempt * 800));
            continue;
          }
          const message =
            reportLoadError instanceof Error ? reportLoadError.message : t.reportFailed;
          if (attempt === retries - 1) {
            if (reportRequestIdRef.current !== requestId) {
              return;
            }
            setActiveReport(null);
            setReportError(message || t.reportFailed);
            return;
          }
          await new Promise((resolve) => window.setTimeout(resolve, 1200 + attempt * 900));
        }
      }
    } finally {
      if (reportRequestIdRef.current === requestId) {
        setIsReportLoading(false);
      }
    }
  }, [t.reportFailed]);

  const pollSnapshotUntilSettled = useCallback(async (
    snapshotId: string,
    options?: { hydrateForm?: boolean; closeHistory?: boolean },
  ) => {
    const requestId = ++snapshotPollRequestIdRef.current;
    const shouldHydrateForm = options?.hydrateForm ?? true;
    const shouldCloseHistory = options?.closeHistory ?? false;
    setIsReportLoading(true);
    setReportError(null);

    for (let attempt = 0; attempt < 360; attempt += 1) {
      const response = await fetchSnapshot(snapshotId);
      if (snapshotPollRequestIdRef.current !== requestId) {
        return;
      }

      setActiveSearch(response);
      if (shouldHydrateForm) {
        hydrateFormFromSearch(response);
      }
      setProviderStatuses(response.provider_statuses);
      if (shouldCloseHistory) {
        setIsHistoryOpen(false);
      }

      if (response.snapshot.status === "ready") {
        await refreshHistory();
        await loadReport(snapshotId);
        return;
      }

      if (response.snapshot.status === "failed") {
        setActiveReport(null);
        setIsReportLoading(false);
        setReportError(null);
        setError(response.snapshot.error_message || "Search failed.");
        await refreshHistory();
        return;
      }

      await wait(Math.min(2500 + attempt * 250, 5000));
    }

    if (snapshotPollRequestIdRef.current === requestId) {
      setError(t.searchInProgress);
      setIsReportLoading(false);
    }
  }, [hydrateFormFromSearch, loadReport, refreshHistory, t.searchInProgress, wait]);

  useEffect(() => {
    void (async () => {
      try {
        const [statusRows, historyResponse] = await Promise.all([
          fetchProviderStatuses(),
          fetchHistory(),
        ]);
        setHistory(historyResponse.items);
        if (historyResponse.items[0]) {
          const initialSnapshot = await fetchSnapshot(historyResponse.items[0].id);
          setActiveSearch(initialSnapshot);
          hydrateFormFromSearch(initialSnapshot);
          setProviderStatuses(initialSnapshot.provider_statuses);
          if (initialSnapshot.snapshot.status === "ready") {
            void loadReport(historyResponse.items[0].id);
          } else if (initialSnapshot.snapshot.status === "processing") {
            void pollSnapshotUntilSettled(historyResponse.items[0].id, { hydrateForm: true });
          } else {
            setError(initialSnapshot.snapshot.error_message || "Search failed.");
          }
        } else {
          setProviderStatuses(statusRows);
        }
      } catch (bootstrapError) {
        setError(
          bootstrapError instanceof Error
            ? bootstrapError.message
            : "Failed to bootstrap dashboard.",
        );
      }
    })();
  }, [hydrateFormFromSearch, loadReport, pollSnapshotUntilSettled]);

  function toggleSource(sourceId: string) {
    setSources((current) =>
      current.includes(sourceId)
        ? current.filter((source) => source !== sourceId)
        : [...current, sourceId],
    );
  }

  function toggleCountry(countryCode: string) {
    setCountriesFilter((current) =>
      current.includes(countryCode)
        ? current.filter((code) => code !== countryCode)
        : [...current, countryCode],
    );
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    snapshotPollRequestIdRef.current += 1;
    setIsSubmitting(true);
    setError(null);
    setActiveReport(null);
    setReportError(null);

    const payload: SearchPayload = {
      query,
      lookback_days: lookbackDays,
      sources,
      countries: countriesFilter,
      limit_per_source: limitPerSource,
    };

    try {
      const response = await runSearch(payload);
      setActiveSearch(response);
      hydrateFormFromSearch(response);
      setProviderStatuses(response.provider_statuses);
      await refreshHistory();
      if (response.snapshot.status === "ready") {
        await loadReport(response.snapshot.id);
      } else if (response.snapshot.status === "processing") {
        void pollSnapshotUntilSettled(response.snapshot.id, { hydrateForm: true });
      } else {
        setError(response.snapshot.error_message || "Search failed.");
      }
    } catch (submitError) {
      setError(
        submitError instanceof Error ? submitError.message : "Failed to run search.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  const openSnapshot = useCallback(async (snapshotId: string) => {
    snapshotPollRequestIdRef.current += 1;
    setLoadingSnapshotId(snapshotId);
    setError(null);
    setIsReportLoading(true);
    setActiveReport(null);
    setReportError(null);
    try {
      const response = await fetchSnapshot(snapshotId);
      setActiveSearch(response);
      hydrateFormFromSearch(response);
      setProviderStatuses(response.provider_statuses);
      if (response.snapshot.status === "ready") {
        setIsHistoryOpen(false);
        void loadReport(snapshotId);
      } else if (response.snapshot.status === "processing") {
        void pollSnapshotUntilSettled(snapshotId, { hydrateForm: true, closeHistory: true });
      } else {
        setIsHistoryOpen(false);
        setError(response.snapshot.error_message || "Search failed.");
        setIsReportLoading(false);
      }
    } catch (snapshotError) {
      setError(
        snapshotError instanceof Error
          ? snapshotError.message
          : "Failed to load snapshot.",
      );
      setIsReportLoading(false);
    } finally {
      setLoadingSnapshotId(null);
    }
  }, [hydrateFormFromSearch, loadReport, pollSnapshotUntilSettled]);

  useEffect(() => {
    if (!history[0] || activeSearch || loadingSnapshotId) {
      return;
    }
    void openSnapshot(history[0].id);
  }, [activeSearch, history, loadingSnapshotId, openSnapshot]);

  const stats = useMemo(() => {
    if (!activeSearch) {
      return {
        total: 0,
        countries: 0,
        languages: 0,
        narratives: 0,
      };
    }

    return {
      total: activeSearch.items.length,
      countries: new Set(
        activeSearch.items.map((item) => item.source_country).filter(Boolean),
      ).size,
      languages: new Set(
        activeSearch.items.map((item) => item.language).filter(Boolean),
      ).size,
      narratives: new Set(activeSearch.items.map((item) => item.narrative)).size,
    };
  }, [activeSearch]);

  const rawHits = providerStatuses.reduce((total, row) => total + row.count, 0);

  const selectedSourcesLabel =
    sources.length === SOURCE_OPTIONS.length
      ? t.allSources
      : `${sources.length} / ${SOURCE_OPTIONS.length}`;

  const selectedCountriesLabel =
    countriesFilter.length === 0
      ? t.allCountries
      : `${countriesFilter.length} / ${COUNTRY_OPTIONS.length}`;

  const sortedNarrativeGroups = useMemo(() => {
    const groups = [...(activeSearch?.narrative_groups ?? [])];
    if (narrativeSortMode === "emotion") {
      const order = { negative: 0, neutral: 1, positive: 2 };
      groups.sort((left, right) => {
        const leftRank = order[left.emotion as keyof typeof order] ?? 3;
        const rightRank = order[right.emotion as keyof typeof order] ?? 3;
        return leftRank - rightRank || right.count - left.count || right.weighted_count - left.weighted_count;
      });
      return groups;
    }
    groups.sort((left, right) => right.weighted_count - left.weighted_count || right.count - left.count);
    return groups;
  }, [activeSearch?.narrative_groups, narrativeSortMode]);

  const selectedNarrativeItems = useMemo(() => {
    if (!selectedNarrative || !activeSearch) {
      return [];
    }
    return activeSearch.items
      .filter((item) => matchesNarrativeGroup(item, selectedNarrative.narrative, selectedNarrative.emotion))
      .sort((left, right) => right.weighted_score - left.weighted_score);
  }, [activeSearch, selectedNarrative]);

  const focusedSegment =
    activeReport?.segment_reports.find((segment) => segment.segment === selectedSegment) ??
    activeReport?.segment_reports[0] ??
    null;

  const groupedSegments = useMemo(() => {
    type SegmentBuckets = {
      main: SegmentReport[];
      atomic: SegmentReport[];
      unknown: SegmentReport[];
    };

    if (!activeReport) {
      return { main: [], atomic: [], unknown: [] } satisfies SegmentBuckets;
    }

    return {
      main: activeReport.segment_reports.filter((segment) =>
        segment.segment === "state_aligned" || segment.segment === "critical_non_state",
      ),
      atomic: activeReport.segment_reports.filter((segment) =>
        segment.segment === "opposition" || segment.segment === "independent" || segment.segment === "western_aligned",
      ),
      unknown: activeReport.segment_reports.filter((segment) => segmentKind(segment.segment) === "unknown"),
    } satisfies SegmentBuckets;
  }, [activeReport]);

  const focusedSegmentItems = useMemo(() => {
    if (!activeSearch || !focusedSegment) {
      return [] as SearchItem[];
    }

    return activeSearch.items
      .filter((item) => itemBelongsToSegment(item, focusedSegment.segment))
      .sort((left, right) => {
        if (right.weighted_score !== left.weighted_score) {
          return right.weighted_score - left.weighted_score;
        }
        return new Date(right.published_at).getTime() - new Date(left.published_at).getTime();
      });
  }, [activeSearch, focusedSegment]);

  const focusedTopicGroups = useMemo(() => {
    if (!focusedSegment || !focusedSegmentItems.length) {
      return [] as SegmentTopicGroup[];
    }

    const reportTopics = new Map(
      focusedSegment.dominant_topics.map((topic) => [normalizeTopicKey(topic.topic), topic]),
    );
    const groups = new Map<string, SearchItem[]>();

    for (const item of focusedSegmentItems) {
      const topic = item.cluster_label ?? item.narrative ?? "general framing";
      const key = normalizeTopicKey(topic);
      const bucket = groups.get(key) ?? [];
      bucket.push(item);
      groups.set(key, bucket);
    }

    return Array.from(groups.entries())
      .map(([key, items]) => {
        const topic = items[0]?.cluster_label ?? items[0]?.narrative ?? "general framing";
        const reportTopic = reportTopics.get(key);
        const emotionCounter = items.reduce<Record<string, number>>((acc, item) => {
          acc[item.emotion] = (acc[item.emotion] ?? 0) + 1;
          return acc;
        }, {});
        const stanceCounter = items.reduce<Record<string, number>>((acc, item) => {
          acc[item.stance] = (acc[item.stance] ?? 0) + 1;
          return acc;
        }, {});
        const countries = new Set(
          items.map((item) => formatCountryLabel(item.source_country, locale)).filter((value) => value !== t.unknown),
        );
        const sources = new Set(items.map((item) => item.source_name));

        return {
          topic,
          items,
          summary: reportTopic?.summary || summarizeTopic(items),
          accents: reportTopic?.accents ?? [],
          mentions: items.length,
          totalInSegment: focusedSegment.item_count,
          sourceCount: sources.size,
          countryCount: countries.size,
          dominantEmotion: pickDominantTone(emotionCounter, "neutral"),
          dominantStance: pickDominantTone(stanceCounter, "unclear"),
        };
      })
      .sort((left, right) => {
        if (right.mentions !== left.mentions) {
          return right.mentions - left.mentions;
        }
        const rightWeight = right.items.reduce((sum, item) => sum + item.weighted_score, 0);
        const leftWeight = left.items.reduce((sum, item) => sum + item.weighted_score, 0);
        return rightWeight - leftWeight;
      });
  }, [focusedSegment, focusedSegmentItems, locale, t.unknown]);

  return (
    <main className="min-h-screen overflow-x-hidden bg-[radial-gradient(circle_at_top_left,_rgba(241,127,55,0.22),_transparent_28%),linear-gradient(180deg,_#f7f2e8_0%,_#efe7d4_50%,_#ece1cd_100%)] text-[var(--ink)]">
      <div className="mx-auto flex min-h-screen max-w-[1600px] min-w-0 flex-col gap-5 px-4 py-4 lg:px-6">
        <section className="rounded-[28px] border border-white/70 bg-white/70 p-3 shadow-[0_18px_60px_rgba(23,38,67,0.12)] backdrop-blur">
          <div className="flex items-center justify-between gap-4">
            <div className="min-w-0 flex-1 md:max-w-[60%]">
              <div className="flex flex-wrap items-center gap-2 rounded-[22px] bg-[linear-gradient(180deg,_rgba(19,38,66,0.98),_rgba(28,53,88,0.95))] px-3 py-3 text-white">
                <span className="text-[10px] font-semibold uppercase tracking-[0.22em] text-white/55">
                  {t.currentRead}
                </span>
                <MetricPill label={t.results} value={stats.total} />
                <MetricPill label={t.countries} value={stats.countries} />
                <MetricPill label={t.languages} value={stats.languages} />
                <MetricPill label={t.narratives} value={stats.narratives} />
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setIsProviderModalOpen(true)}
                className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-black/10 bg-white text-[var(--ink)] transition hover:border-[var(--ink)] hover:bg-[rgba(19,38,66,0.04)]"
                aria-label={t.providerStatusesTitle}
                title={t.providerStatusesTitle}
              >
                <StatusListIcon />
              </button>
              <button
                type="button"
                onClick={() => setIsHistoryOpen(true)}
                className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-black/10 bg-white text-[var(--ink)] transition hover:border-[var(--ink)] hover:bg-[rgba(19,38,66,0.04)]"
                aria-label={t.openSnapshots}
                title={t.openSnapshots}
              >
                <CameraIcon />
              </button>
              <div className="inline-flex rounded-full border border-black/10 bg-white p-1">
              {(["ru", "en"] as const).map((language) => (
                <button
                  key={language}
                  type="button"
                  onClick={() => setLocale(language)}
                  className={`rounded-full px-3 py-2 text-xs font-semibold transition ${
                    locale === language
                      ? "bg-[var(--ink)] text-white"
                      : "text-[var(--muted)]"
                  }`}
                >
                  {language.toUpperCase()}
                </button>
              ))}
              </div>
            </div>
          </div>
        </section>

        <section className="relative z-[120] isolate overflow-visible rounded-[28px] border border-white/70 bg-white/70 p-4 shadow-[0_18px_60px_rgba(23,38,67,0.1)] backdrop-blur">
          <form
            className="grid gap-3 lg:grid-cols-[minmax(320px,2fr)_100px_110px_minmax(220px,1fr)_minmax(240px,1fr)_56px_56px] lg:items-stretch"
            onSubmit={handleSubmit}
          >
            <label className="flex h-full flex-col gap-2">
              <span className="flex min-h-[14px] items-end text-[10px] font-semibold uppercase tracking-[0.22em] text-[var(--muted)]">
                {t.query}
              </span>
              <input
                aria-label={t.query}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                className="h-[52px] w-full rounded-[18px] border border-black/10 bg-[rgba(247,242,232,0.72)] px-4 py-3 text-sm outline-none transition focus:border-[var(--accent)] focus:ring-2 focus:ring-[rgba(220,105,35,0.16)]"
                placeholder={t.queryPlaceholder}
              />
            </label>

            <label className="flex h-full flex-col gap-2">
              <span className="flex min-h-[14px] items-end text-[10px] font-semibold uppercase tracking-[0.22em] text-[var(--muted)]">
                {t.lookback}
              </span>
              <input
                type="number"
                min={1}
                max={365}
                value={lookbackDays}
                onChange={(event) => setLookbackDays(Number(event.target.value))}
                className="h-[52px] w-full rounded-[18px] border border-black/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-[var(--accent)]"
              />
            </label>

            <label className="flex h-full flex-col gap-2">
              <span className="flex min-h-[14px] items-end text-[10px] font-semibold uppercase tracking-[0.22em] text-[var(--muted)]">
                {t.resultsPerSource}
              </span>
              <input
                type="number"
                min={10}
                max={200}
                value={limitPerSource}
                onChange={(event) => setLimitPerSource(Number(event.target.value))}
                className="h-[52px] w-full rounded-[18px] border border-black/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-[var(--accent)]"
              />
            </label>

            <div className="relative flex h-full flex-col gap-2">
              <p className="flex min-h-[14px] items-end text-[10px] font-semibold uppercase tracking-[0.22em] text-[var(--muted)]">
                {t.countriesFilter}
              </p>
              <details className="relative z-[220] mt-auto h-[52px] open:z-[340]">
                <summary className="flex h-[52px] cursor-pointer list-none items-center justify-between rounded-[18px] border border-black/10 bg-white px-4 py-3 text-sm font-semibold text-[var(--ink)] [&::-webkit-details-marker]:hidden">
                  <span className="truncate">
                    {t.selectedCountries}: {selectedCountriesLabel}
                  </span>
                </summary>
                <div className="absolute left-0 right-0 z-[360] mt-2 grid max-h-72 gap-2 overflow-auto rounded-[22px] border border-black/10 bg-white p-3 shadow-[0_18px_45px_rgba(23,38,67,0.14)]">
                  {COUNTRY_OPTIONS.map((option) => {
                    const enabled = countriesFilter.includes(option.code);
                    return (
                      <label
                        key={option.code}
                        className="flex items-center justify-between rounded-[16px] bg-[rgba(247,242,232,0.72)] px-3 py-3 text-sm"
                      >
                        <span className="font-semibold">{option.label[locale]}</span>
                        <input
                          type="checkbox"
                          checked={enabled}
                          onChange={() => toggleCountry(option.code)}
                          className="h-4 w-4 accent-[var(--accent)]"
                        />
                      </label>
                    );
                  })}
                </div>
              </details>
            </div>

            <div className="relative flex h-full flex-col gap-2">
              <p className="flex min-h-[14px] items-end text-[10px] font-semibold uppercase tracking-[0.22em] text-[var(--muted)]">
                {t.sources}
              </p>
              <details className="relative z-[220] mt-auto h-[52px] open:z-[340]">
                <summary className="flex h-[52px] cursor-pointer list-none items-center justify-between rounded-[18px] border border-black/10 bg-white px-4 py-3 text-sm font-semibold text-[var(--ink)] [&::-webkit-details-marker]:hidden">
                  <span className="truncate">
                    {t.selectedSources}: {selectedSourcesLabel}
                  </span>
                </summary>
                <div className="absolute left-0 right-0 z-[360] mt-2 grid max-h-72 gap-2 overflow-auto rounded-[22px] border border-black/10 bg-white p-3 shadow-[0_18px_45px_rgba(23,38,67,0.14)]">
                  {SOURCE_OPTIONS.map((option) => {
                    const enabled = sources.includes(option.id);
                    return (
                      <label
                        key={option.id}
                        className="flex items-center justify-between rounded-[16px] bg-[rgba(247,242,232,0.72)] px-3 py-3 text-sm"
                      >
                        <span className="font-semibold">{option.label[locale]}</span>
                        <input
                          type="checkbox"
                          checked={enabled}
                          onChange={() => toggleSource(option.id)}
                          className="h-4 w-4 accent-[var(--accent)]"
                        />
                      </label>
                    );
                  })}
                </div>
              </details>
            </div>

            <div className="flex h-full items-end justify-end">
              <button
                type="submit"
                disabled={isSubmitting || isSearchProcessing || sources.length === 0}
                title={t.runSearchTooltip}
                aria-label={t.runSearchTooltip}
                className={`${iconButtonClass} bg-[linear-gradient(135deg,_#1a3359,_#dc691f)] text-white`}
              >
                <SearchIcon active={isSubmitting} />
              </button>
            </div>
            <div className="flex h-full items-end justify-end">
              {activeSearch ? (
                <details className="relative h-[52px] open:z-[340]">
                  <summary
                    title={t.exportMenuTooltip}
                    aria-label={t.exportMenuTooltip}
                    className={`${iconButtonClass} group list-none border border-[var(--ink)] bg-white text-[var(--ink)] hover:bg-[var(--ink)] hover:text-white [&::-webkit-details-marker]:hidden ${activeSearch.snapshot.status !== "ready" ? "pointer-events-none opacity-40" : ""}`}
                  >
                    <ExcelIcon />
                  </summary>
                  <div className="absolute right-0 z-[360] mt-2 grid min-w-[180px] gap-2 rounded-[20px] border border-black/10 bg-white p-2 shadow-[0_18px_45px_rgba(23,38,67,0.14)]">
                    <a
                      href={exportSnapshotUrl(activeSearch.snapshot.id, "excel")}
                      className="rounded-[14px] px-3 py-3 text-sm font-semibold text-[var(--ink)] transition hover:bg-[rgba(19,38,66,0.06)]"
                    >
                      {t.exportExcel}
                    </a>
                    <a
                      href={exportSnapshotUrl(activeSearch.snapshot.id, "docx")}
                      className="rounded-[14px] px-3 py-3 text-sm font-semibold text-[var(--ink)] transition hover:bg-[rgba(19,38,66,0.06)]"
                    >
                      {t.exportDocx}
                    </a>
                  </div>
                </details>
              ) : (
                <div className="h-[52px] w-[56px]" />
              )}
            </div>

            {isSubmitting || isSearchProcessing ? (
              <div className="w-full lg:col-span-6">
                <SearchProgress
                  locale={locale}
                  activeIndex={searchPhaseIndex}
                  heading={t.searchInProgress}
                />
              </div>
            ) : null}
          </form>

          {error ? (
            <div className="mt-3 rounded-[18px] border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-900">
              {t.errorPrefix}: {error}
            </div>
          ) : null}
        </section>

        <section className="relative z-0 grid min-w-0 gap-5">
          <section className="rounded-[28px] border border-white/70 bg-white/70 p-4 shadow-[0_18px_60px_rgba(23,38,67,0.1)] backdrop-blur">
            <div className="flex items-center justify-between gap-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[var(--muted)]">
                {t.narrativesShort}
              </p>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    setNarrativeSortMode((current) => (current === "signal" ? "emotion" : "signal"));
                  }}
                  title={t.sortByMood}
                  aria-label={t.sortByMood}
                  className={`inline-flex h-9 w-9 items-center justify-center rounded-full border border-black/10 bg-white text-[var(--ink)] transition duration-200 hover:-translate-y-0.5 hover:shadow-[0_10px_24px_rgba(23,38,67,0.14)] ${
                    narrativeSortMode === "emotion" ? "border-[var(--accent)] text-[var(--accent)]" : ""
                  }`}
                >
                  <SortIcon />
                </button>
                {activeSearch ? (
                  <div className="rounded-full bg-[rgba(19,38,66,0.08)] px-3 py-2 text-sm font-semibold text-[var(--ink)]">
                    {activeSearch.narrative_groups.length} {t.clusters}
                  </div>
                ) : null}
                <button
                  type="button"
                  onClick={() => setIsNarrativesOpen((current) => !current)}
                  aria-label={isNarrativesOpen ? t.collapse : t.expand}
                  className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-black/10 bg-white text-[var(--ink)] transition duration-200 hover:-translate-y-0.5 hover:shadow-[0_10px_24px_rgba(23,38,67,0.14)]"
                >
                  <ChevronIcon open={isNarrativesOpen} />
                </button>
              </div>
            </div>
            <AnimatedCollapse open={isNarrativesOpen}>
              {activeSearch?.narrative_groups.length ? (
                <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                  {sortedNarrativeGroups.map((group) => (
                    <button
                      key={`${group.narrative}-${group.emotion}`}
                      type="button"
                      onClick={() => setSelectedNarrative({ narrative: group.narrative, emotion: group.emotion })}
                      title={t.openNarrative}
                      className="rounded-[20px] border border-black/[0.06] bg-[linear-gradient(180deg,_rgba(247,242,232,0.7),_white)] p-4 text-left transition duration-200 hover:-translate-y-0.5 hover:border-[var(--ink)] hover:shadow-[0_16px_36px_rgba(23,38,67,0.1)]"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <h3 className="font-display text-xl tracking-[-0.03em]">
                          {formatNarrativeLabel(group.narrative, locale)}
                        </h3>
                        <span
                          className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] ${emotionTone(
                            group.emotion,
                          )}`}
                        >
                          {formatEmotion(group.emotion, locale)}
                        </span>
                      </div>
                      <p className="mt-3 text-2xl font-semibold text-[var(--ink)]">
                        {group.count}
                        <span className="ml-2 text-sm font-medium text-[var(--muted)]">
                          {t.items}
                        </span>
                      </p>
                      <p className="mt-3 line-clamp-3 text-sm leading-6 text-[var(--muted)]">
                        {t.weightedSignal}: {group.weighted_count}. {t.topSources}: {group.top_sources.join(", ")}
                      </p>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="mt-4">
                  <EmptyPanel copy={t.narrativesEmpty} />
                </div>
              )}
            </AnimatedCollapse>
          </section>

          <div className="min-w-0">
            <section className="rounded-[28px] border border-white/70 bg-white/70 p-5 shadow-[0_18px_60px_rgba(23,38,67,0.1)] backdrop-blur">
              {activeSearch ? (
                <div className="mb-5 rounded-[22px] border border-black/[0.06] bg-[rgba(247,242,232,0.72)] p-4">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[var(--muted)]">
                    {t.strategy}
                  </p>
                  <p className="mt-3 text-sm leading-6 text-[var(--muted)]">
                    {t.analysisMode}: {formatAnalysisValue(activeSearch.analysis_mode, locale)}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
                    {t.rawHits}: {rawHits} → {stats.total} {t.results.toLowerCase()}
                  </p>
                  <p className="mt-3 text-sm leading-6 text-[var(--muted)]">
                    {t.expandedQuery}: {activeSearch.query_plan.expanded_query}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
                    {t.anchorTerms}: {activeSearch.query_plan.anchor_terms.join(", ")}
                  </p>
                </div>
              ) : null}

              {activeSearch ? (
                <div className="mb-5 rounded-[22px] border border-black/[0.06] bg-white p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[var(--muted)]">
                      {t.report}
                    </p>
                    {activeReport ? (
                      <span className="rounded-full bg-[rgba(19,38,66,0.08)] px-4 py-2 text-sm font-semibold text-[var(--ink)]">
                        {stats.total}/{rawHits}
                      </span>
                    ) : null}
                  </div>

                  {isReportLoading ? (
                    <div className="mt-4">
                      <EmptyPanel copy={t.reportLoading} />
                    </div>
                  ) : activeReport ? (
                    <div className="mt-5 grid gap-5">
                      <div className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
                        <div className="rounded-[20px] bg-[rgba(247,242,232,0.72)] p-4">
                          <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--muted)]">
                            {t.reportOverview}
                          </p>
                          <h3 className="mt-3 font-display text-[30px] leading-[1.02] tracking-[-0.04em] text-[var(--ink)]">
                            {activeReport.report_title}
                          </h3>
                          <p className="mt-4 line-clamp-4 text-sm leading-7 text-[var(--muted)]">
                            <AutoTranslatedText text={activeReport.overview} locale={locale} />
                          </p>

                          <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                            <CoverageMetric
                              label={t.classifiedItems}
                              value={`${activeReport.registry_coverage.classified_items}/${activeReport.registry_coverage.total_items}`}
                            />
                            <CoverageMetric
                              label={t.classifiedSources}
                              value={`${activeReport.registry_coverage.classified_sources}/${activeReport.registry_coverage.total_sources}`}
                            />
                            <CoverageMetric
                              label={t.sourceCoverageBySegment}
                              value={countEntries(activeReport.registry_coverage.segment_breakdown)}
                            />
                            <CoverageMetric
                              label={t.countriesList}
                              value={countEntries(activeReport.registry_coverage.country_breakdown)}
                            />
                          </div>

                          <div className="mt-5 grid gap-3 md:grid-cols-3">
                            <CompactBreakdown
                              title={t.sourceTypes}
                              rows={sortedBreakdownEntries(activeReport.registry_coverage.source_type_breakdown).map(
                                ([label, value]) => ({
                                  label: formatSourceTypeLabel(label, locale),
                                  value,
                                }),
                              )}
                              emptyLabel={t.noSignal}
                            />
                            <CompactBreakdown
                              title={t.sourceCoverageBySegment}
                              rows={sortedBreakdownEntries(activeReport.registry_coverage.segment_breakdown).map(
                                ([label, value]) => ({
                                  label: formatSegmentLabel(label, locale),
                                  value,
                                }),
                              )}
                              emptyLabel={t.noSignal}
                            />
                            <CompactBreakdown
                              title={t.countryCoverageBySegment}
                              rows={sortedBreakdownEntries(activeReport.registry_coverage.country_breakdown).map(
                                ([label, value]) => ({
                                  label: formatCountryLabel(label, locale),
                                  value,
                                }),
                              )}
                              emptyLabel={t.noSignal}
                            />
                          </div>
                        </div>

                        <div className="grid gap-4">
                          <div className="rounded-[20px] bg-[rgba(247,242,232,0.72)] p-4">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--muted)]">
                              {t.crossSegmentGaps}
                            </p>
                            <div className="mt-3 grid gap-2">
                              {activeReport.cross_segment_gaps.length ? (
                                activeReport.cross_segment_gaps.slice(0, 4).map((gap) => (
                                  <p key={gap} className="text-sm leading-6 text-[var(--muted)]">
                                    {cleanCoverageGapText(gap)}
                                  </p>
                                ))
                              ) : (
                                <p className="text-sm leading-6 text-[var(--muted)]">
                                  {t.noSignal}
                                </p>
                              )}
                            </div>
                          </div>

                          <div className="rounded-[20px] bg-[rgba(247,242,232,0.72)] p-4">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--muted)]">
                              {t.uncoveredSources}
                            </p>
                            <div className="mt-3 flex flex-wrap gap-2">
                              {activeReport.registry_coverage.uncovered_sources.length ? (
                                activeReport.registry_coverage.uncovered_sources.slice(0, 8).map((source) => (
                                  <span
                                    key={source}
                                    className="rounded-full bg-white px-3 py-2 text-sm text-[var(--muted)]"
                                  >
                                    {source}
                                  </span>
                                ))
                              ) : (
                                <p className="text-sm leading-6 text-[var(--muted)]">
                                  {t.noSignal}
                                </p>
                              )}
                            </div>
                          </div>

                          <div className="rounded-[20px] bg-[rgba(247,242,232,0.72)] p-4">
                            <button
                              type="button"
                              onClick={() => setIsQuotesOpen((current) => !current)}
                              className="flex w-full items-center justify-between gap-3 text-left"
                            >
                              <div>
                                <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--muted)]">
                                  {t.keyQuotes}
                                </p>
                                <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
                                  {t.keyQuotesHint}
                                </p>
                              </div>
                              <div className="flex items-center gap-2">
                                <span className="rounded-full bg-white px-3 py-2 text-sm font-semibold text-[var(--ink)]">
                                  {activeReport.key_quotes.length}
                                </span>
                                <ChevronIcon open={isQuotesOpen} />
                              </div>
                            </button>
                            <AnimatedCollapse open={isQuotesOpen}>
                              <div className="mt-3 grid gap-3">
                                {activeReport.key_quotes.length ? (
                                  activeReport.key_quotes.slice(0, 8).map((quote) => (
                                    <QuoteItem
                                      key={`${quote.source_name}-${quote.quote}`}
                                      quote={quote}
                                      locale={locale}
                                    />
                                  ))
                                ) : (
                                  <p className="text-sm leading-6 text-[var(--muted)]">
                                    {t.noSignal}
                                  </p>
                                )}
                              </div>
                            </AnimatedCollapse>
                          </div>
                        </div>
                      </div>

                      <div className="grid gap-4 xl:grid-cols-[minmax(250px,0.42fr)_minmax(0,1.58fr)]">
                        <div className="rounded-[20px] border border-black/[0.06] bg-white p-3.5">
                          <div className="flex items-center justify-between gap-3">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[var(--muted)]">
                              {t.reportSegments}
                            </p>
                            <span className="text-sm text-[var(--muted)]">
                              {activeReport.segment_reports.length}
                            </span>
                          </div>

                          <div className="mt-3 grid gap-3">
                            {groupedSegments.main.length ? (
                              <SegmentCluster
                                title={t.mainSegments}
                                segments={groupedSegments.main}
                                activeSegment={focusedSegment?.segment ?? null}
                                locale={locale}
                                onSelect={setSelectedSegment}
                              />
                            ) : null}
                            {groupedSegments.atomic.length ? (
                              <SegmentCluster
                                title={t.detailLayer}
                                segments={groupedSegments.atomic}
                                activeSegment={focusedSegment?.segment ?? null}
                                locale={locale}
                                onSelect={setSelectedSegment}
                              />
                            ) : null}
                            {groupedSegments.unknown.length ? (
                              <SegmentCluster
                                title={t.pendingLayer}
                                segments={groupedSegments.unknown}
                                activeSegment={focusedSegment?.segment ?? null}
                                locale={locale}
                                onSelect={setSelectedSegment}
                              />
                            ) : null}
                          </div>
                        </div>

                        <div className="rounded-[20px] border border-black/[0.06] bg-[linear-gradient(180deg,_rgba(247,242,232,0.72),_white)] p-4">
                          <div className="flex items-center justify-between gap-3">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[var(--muted)]">
                              {t.segmentFocus}
                            </p>
                            {focusedSegment ? (
                              <span className="rounded-full bg-[rgba(19,38,66,0.08)] px-3 py-2 text-sm font-semibold text-[var(--ink)]">
                                {focusedSegmentItems.length}
                              </span>
                            ) : null}
                          </div>

                          {focusedSegment ? (
                            <div className="mt-4 grid gap-4">
                              <div>
                                <div className="flex flex-wrap items-center gap-3">
                                  <h3 className="font-display text-[28px] leading-[1.02] tracking-[-0.04em] text-[var(--ink)]">
                                    {formatSegmentLabel(focusedSegment.segment, locale)}
                                  </h3>
                                  <span
                                    className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] ${complementarityTone(
                                      focusedSegment.complementarity,
                                    )}`}
                                  >
                                    {formatComplementarity(focusedSegment.complementarity, locale)}
                                  </span>
                                </div>
                                <p className="mt-3 text-sm leading-6 text-[var(--muted)]">
                                  <AutoTranslatedText text={focusedSegment.overview} locale={locale} />
                                </p>
                              </div>

                              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                                <CoverageMetric label={t.results} value={focusedSegment.item_count} compact />
                                <CoverageMetric label={t.totalSources} value={focusedSegment.source_count} compact />
                                <CoverageMetric
                                  label={t.countriesList}
                                  value={focusedSegment.countries.length || t.unknown}
                                  compact
                                />
                                <CoverageMetric
                                  label={t.narrativesShort}
                                  value={focusedTopicGroups.length}
                                  compact
                                />
                              </div>

                              <div className="grid items-start gap-3 xl:grid-cols-[0.78fr_1.22fr]">
                                <div className="grid content-start gap-3 self-start">
                                  <TagBlock title={t.sourceExamples} values={focusedSegment.source_examples} emptyLabel={t.noSignal} />
                                  <TagBlock
                                    title={t.sourceTypes}
                                    values={focusedSegment.source_types.map((value) => formatSourceTypeLabel(value, locale))}
                                    emptyLabel={t.noSignal}
                                  />
                                  <TagBlock
                                    title={t.countriesList}
                                    values={focusedSegment.countries.map((value) => formatCountryLabel(value, locale))}
                                    emptyLabel={t.noSignal}
                                  />
                                  <TagBlock
                                    title={t.omittedTopics}
                                    values={focusedSegment.omitted_topics.map((value) => formatNarrativeLabel(value, locale))}
                                    emptyLabel={t.noSignal}
                                  />
                                </div>

                                <div className="grid gap-3">
                                  <div className="rounded-[18px] border border-black/[0.06] bg-white p-4">
                                    <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--muted)]">
                                      {t.topicCoverage}
                                    </p>
                                    <div className="mt-4 grid gap-3">
                                      {focusedTopicGroups.length ? (
                                        focusedTopicGroups.map((topicGroup, index) => (
                                          <TopicArticleAccordion
                                            key={`${focusedSegment.segment}-${topicGroup.topic}`}
                                            locale={locale}
                                            topicGroup={topicGroup}
                                            defaultOpen={index === 0}
                                          />
                                        ))
                                      ) : (
                                        <EmptyPanel copy={t.noSignal} />
                                      )}
                                    </div>
                                  </div>
                                </div>
                              </div>
                            </div>
                          ) : (
                            <div className="mt-4">
                              <EmptyPanel copy={t.noSignal} />
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  ) : reportError ? (
                    <div className="mt-4 rounded-[18px] border border-[rgba(208,77,77,0.2)] bg-[rgba(255,237,237,0.88)] px-4 py-4 text-sm leading-6 text-[#b24545]">
                      {t.errorPrefix}: {reportError}
                    </div>
                  ) : (
                    <div className="mt-4">
                      <EmptyPanel copy={t.reportEmpty} />
                    </div>
                  )}
                </div>
              ) : null}

              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[var(--muted)]">
                  {t.resultsTable}
                </p>
                {activeSearch ? (
                  <p className="text-sm leading-6 text-[var(--muted)]">
                    {t.snapshotCreatedAt}: {formatDate(activeSearch.snapshot.created_at, locale)}
                  </p>
                ) : null}
              </div>

              {activeSearch?.items.length ? (
                <div className="mt-5 overflow-hidden rounded-[24px] border border-black/[0.06]">
                  <div className="max-h-[560px] overflow-auto">
                    <table className="min-w-full border-separate border-spacing-0 text-left">
                      <thead className="sticky top-0 z-10 bg-[var(--ink)] text-xs uppercase tracking-[0.18em] text-white">
                        <tr>
                          <th className="px-4 py-3">{t.published}</th>
                          <th className="px-4 py-3">{t.source}</th>
                          <th className="px-4 py-3">{t.headline}</th>
                          <th className="px-4 py-3">{t.pivotSummary}</th>
                          <th className="px-4 py-3">{t.narrative}</th>
                          <th className="px-4 py-3">{t.emotion}</th>
                          <th className="px-4 py-3">{t.stance}</th>
                          <th className="px-4 py-3">{t.alignment}</th>
                          <th className="px-4 py-3">{t.originality}</th>
                          <th className="px-4 py-3">{t.weight}</th>
                        </tr>
                      </thead>
                      <tbody className="bg-white">
                        {activeSearch.items.map((item, index) => (
                          <tr
                            key={item.id}
                            className={index % 2 === 0 ? "bg-white" : "bg-[rgba(247,242,232,0.5)]"}
                          >
                            <td className="px-4 py-4 align-top text-sm text-[var(--muted)]">
                              <div>{formatDate(item.published_at, locale)}</div>
                              <div className="mt-2 text-xs uppercase tracking-[0.16em]">
                                {item.provider}
                              </div>
                            </td>
                            <td className="px-4 py-4 align-top">
                              <div className="font-semibold">{item.source_name}</div>
                              <div className="mt-2 text-xs uppercase tracking-[0.16em] text-[var(--muted)]">
                                {formatCountryLabel(item.source_country, locale)} / {item.language ?? t.unknown}
                              </div>
                              {item.is_curated_source ? (
                                <div className="mt-2 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--accent)]">
                                  {t.curated}
                                </div>
                              ) : null}
                            </td>
                            <td className="px-4 py-4 align-top">
                              <a
                                href={item.url}
                                target="_blank"
                                rel="noreferrer"
                                className="font-semibold leading-6 text-[var(--ink)] underline-offset-4 hover:underline"
                              >
                                <HoverTranslateText text={item.title} locale={locale} languageHint={item.language} />
                              </a>
                              <div className="mt-2 text-xs uppercase tracking-[0.16em] text-[var(--muted)]">
                                {formatNarrativeLabel(item.cluster_label ?? item.narrative, locale)} /{" "}
                                {formatAnalysisValue(item.analysis_method, locale)}
                              </div>
                            </td>
                            <td className="px-4 py-4 align-top text-sm leading-6 text-[var(--muted)]">
                              <div>
                                <AutoTranslatedText text={item.pivot_summary} locale={locale} languageHint={item.pivot_language ?? item.language} />
                              </div>
                              {item.pivot_summary !== item.summary ? (
                                <div className="mt-3 text-xs leading-5 text-[var(--muted)]/80">
                                  {t.original}:{" "}
                                  <HoverTranslateText text={item.summary} locale={locale} languageHint={item.language} />
                                </div>
                              ) : null}
                            </td>
                            <td className="px-4 py-4 align-top">
                              <span className="rounded-full bg-[rgba(19,38,66,0.08)] px-3 py-1 text-sm font-semibold capitalize text-[var(--ink)]">
                                {formatNarrativeLabel(item.narrative, locale)}
                              </span>
                            </td>
                            <td className="px-4 py-4 align-top">
                              <span
                                className={`rounded-full px-3 py-1 text-sm font-semibold capitalize ${emotionTone(
                                  item.emotion,
                                )}`}
                              >
                                {formatEmotion(item.emotion, locale)}
                              </span>
                            </td>
                            <td className="px-4 py-4 align-top">
                              <span
                                className={`rounded-full px-3 py-1 text-sm font-semibold capitalize ${stanceTone(
                                  item.stance,
                                )}`}
                              >
                                {formatStance(item.stance, locale)}
                              </span>
                            </td>
                            <td className="px-4 py-4 align-top">
                              <span
                                className={`rounded-full px-3 py-1 text-sm font-semibold uppercase ${alignmentTone(
                                  item.query_alignment,
                                )}`}
                              >
                                {formatAlignment(item.query_alignment, locale)}
                              </span>
                            </td>
                            <td className="px-4 py-4 align-top">
                              <span
                                className={`rounded-full px-3 py-1 text-sm font-semibold capitalize ${originalityTone(
                                  item.originality,
                                )}`}
                              >
                                {formatOriginality(item.originality, locale)}
                              </span>
                            </td>
                            <td className="px-4 py-4 align-top text-sm font-semibold text-[var(--ink)]">
                              {item.weighted_score}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : (
                <div className="mt-5">
                  <EmptyPanel copy={t.tableEmpty} />
                </div>
              )}
            </section>
          </div>
        </section>
        {isHistoryOpen ? (
          <SnapshotModal
            locale={locale}
            title={t.historyShort}
            snapshots={history}
            activeSnapshotId={activeSearch?.snapshot.id ?? null}
            loadingSnapshotId={loadingSnapshotId}
            onClose={() => setIsHistoryOpen(false)}
            onOpenSnapshot={(snapshotId) => void openSnapshot(snapshotId)}
          />
        ) : null}
        {isProviderModalOpen ? (
          <ProviderStatusModal
            locale={locale}
            title={t.providerStatusesTitle}
            statuses={providerStatuses}
            onClose={() => setIsProviderModalOpen(false)}
          />
        ) : null}
        {selectedNarrative ? (
          <NarrativeModal
            locale={locale}
            narrative={selectedNarrative}
            items={selectedNarrativeItems}
            onClose={() => setSelectedNarrative(null)}
          />
        ) : null}
      </div>
    </main>
  );
}

function MetricPill({ label, value }: { label: string; value: number }) {
  return (
    <div className="inline-flex items-center gap-2 rounded-full bg-white/[0.08] px-3 py-1.5">
      <span className="text-[10px] uppercase tracking-[0.2em] text-white/55">
        {label}
      </span>
      <span className="text-lg font-semibold text-white">{value}</span>
    </div>
  );
}

function CameraIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4.5 w-4.5" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M4.75 7.75h3l1.4-2h5.7l1.4 2h3A1.75 1.75 0 0 1 21 9.5v8.75A1.75 1.75 0 0 1 19.25 20H4.75A1.75 1.75 0 0 1 3 18.25V9.5A1.75 1.75 0 0 1 4.75 7.75Z" />
      <circle cx="12" cy="13" r="3.4" />
    </svg>
  );
}

function SearchIcon({ active = false }: { active?: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={`h-5 w-5 transition-colors duration-200 ${active ? "animate-pulse" : ""}`}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="11" cy="11" r="6.5" />
      <path d="M16 16l4.25 4.25" />
    </svg>
  );
}

function ExcelIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      className="h-5 w-5 text-[var(--ink)] transition-colors duration-200 group-hover:text-white"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M12 4v10" />
      <path d="m8.5 10.5 3.5 3.5 3.5-3.5" />
      <path d="M5 15.5v2.25A1.25 1.25 0 0 0 6.25 19h11.5A1.25 1.25 0 0 0 19 17.75V15.5" />
    </svg>
  );
}

function StatusListIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      className="h-5 w-5 transition-colors duration-200"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M9 6h10" />
      <path d="M9 12h10" />
      <path d="M9 18h10" />
      <circle cx="5" cy="6" r="1.25" fill="currentColor" stroke="none" />
      <circle cx="5" cy="12" r="1.25" fill="currentColor" stroke="none" />
      <circle cx="5" cy="18" r="1.25" fill="currentColor" stroke="none" />
    </svg>
  );
}

function SortIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      className="h-4.5 w-4.5"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M7 6h10" />
      <path d="M5 12h8" />
      <path d="M9 18h10" />
    </svg>
  );
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={`h-4.5 w-4.5 transition duration-300 ${open ? "rotate-180" : ""}`}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="m6 9 6 6 6-6" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4.5 w-4.5" fill="none" stroke="currentColor" strokeWidth="1.9">
      <path d="M6 6l12 12" />
      <path d="M18 6 6 18" />
    </svg>
  );
}

function SearchProgress({
  locale,
  activeIndex,
  heading,
}: {
  locale: Locale;
  activeIndex: number;
  heading: string;
}) {
  const phases = SEARCH_PHASES[locale];

  return (
    <div className="rounded-[22px] border border-black/[0.06] bg-[rgba(247,242,232,0.72)] p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[var(--muted)]">
          {heading}
        </p>
        <span className="h-2 w-2 rounded-full bg-[var(--accent)] animate-pulse" />
      </div>
      <div className="mt-4 h-2 overflow-hidden rounded-full bg-white">
        <div
          className="h-full rounded-full bg-[linear-gradient(135deg,_#1a3359,_#dc691f)] transition-all duration-700"
          style={{ width: `${((activeIndex + 1) / phases.length) * 100}%` }}
        />
      </div>
      <div className="mt-4 grid gap-2">
        {phases.map((phase, index) => {
          const isActive = index === activeIndex;
          const isPassed = index < activeIndex;

          return (
            <div
              key={phase}
              className={`flex items-center justify-between rounded-[16px] px-3 py-3 text-sm transition ${
                isActive
                  ? "bg-[rgba(26,51,89,0.1)] text-[var(--ink)]"
                  : isPassed
                    ? "bg-white text-[var(--muted)]"
                    : "bg-white/70 text-[var(--muted)]"
              }`}
            >
              <span className="font-medium">{phase}</span>
              <span
                className={`text-xs font-semibold uppercase tracking-[0.16em] ${
                  isActive
                    ? "text-[var(--accent)]"
                    : isPassed
                      ? "text-emerald-700"
                      : "text-[var(--muted)]"
                }`}
              >
                {isActive ? "..." : isPassed ? "ok" : ""}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function EmptyPanel({ copy }: { copy: string }) {
  return (
    <div className="rounded-[22px] border border-dashed border-black/10 bg-white/70 px-5 py-8 text-sm leading-7 text-[var(--muted)]">
      {copy}
    </div>
  );
}

function AnimatedCollapse({
  open,
  children,
}: {
  open: boolean;
  children: ReactNode;
}) {
  return (
    <div
      className={`grid overflow-hidden transition-all duration-300 ease-out ${
        open ? "mt-4 grid-rows-[1fr] opacity-100" : "mt-0 grid-rows-[0fr] opacity-0"
      }`}
    >
      <div className="min-h-0 overflow-hidden">{children}</div>
    </div>
  );
}

function CoverageMetric({
  label,
  value,
  compact = false,
}: {
  label: string;
  value: string | number;
  compact?: boolean;
}) {
  return (
    <div
      className={`rounded-[18px] bg-white px-4 py-3 ${
        compact ? "min-h-[84px]" : "min-h-[96px]"
      }`}
    >
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--muted)]">
        {label}
      </p>
      <p
        className={`mt-3 font-semibold tracking-[-0.03em] text-[var(--ink)] ${
          compact ? "text-2xl leading-none" : "text-[28px] leading-none"
        }`}
      >
        {value}
      </p>
    </div>
  );
}

function CompactBreakdown({
  title,
  rows,
  emptyLabel,
}: {
  title: string;
  rows: Array<{ label: string; value: number }>;
  emptyLabel: string;
}) {
  return (
    <div className="rounded-[18px] bg-white p-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--muted)]">
        {title}
      </p>
      <div className="mt-3 grid gap-2">
        {rows.length ? (
          rows.slice(0, 4).map((row) => (
            <div
              key={`${title}-${row.label}`}
              className="flex items-center justify-between gap-3 text-sm text-[var(--muted)]"
            >
              <span className="truncate">{row.label}</span>
              <span className="rounded-full bg-[rgba(19,38,66,0.08)] px-2.5 py-1 font-semibold text-[var(--ink)]">
                {row.value}
              </span>
            </div>
          ))
        ) : (
          <p className="text-sm leading-6 text-[var(--muted)]">{emptyLabel}</p>
        )}
      </div>
    </div>
  );
}

function TagBlock({
  title,
  values,
  emptyLabel,
}: {
  title: string;
  values: string[];
  emptyLabel: string;
}) {
  return (
    <div className="h-fit self-start rounded-[18px] border border-black/[0.06] bg-white p-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--muted)]">
        {title}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        {values.length ? (
          values.slice(0, 6).map((value) => (
            <span
              key={`${title}-${value}`}
              className="rounded-full bg-[rgba(247,242,232,0.72)] px-3 py-2 text-sm leading-5 text-[var(--muted)]"
            >
              {value}
            </span>
          ))
        ) : (
          <p className="text-sm leading-6 text-[var(--muted)]">{emptyLabel}</p>
        )}
      </div>
    </div>
  );
}

function AutoTranslatedText({
  text,
  locale,
  languageHint,
}: {
  text: string;
  locale: Locale;
  languageHint?: string | null;
}) {
  const [translation, setTranslation] = useState<string | null>(null);
  const [resolvedKey, setResolvedKey] = useState<string | null>(null);
  const normalized = (text || "").trim();
  const cacheKey = `${languageHint ?? "auto"}::${normalized}`;
  const cachedTranslation = translationCache.get(cacheKey);

  useEffect(() => {
    let cancelled = false;
    if (!normalized || !shouldOfferTranslation(normalized, locale, languageHint)) {
      return;
    }
    if (cachedTranslation !== undefined) {
      return;
    }

    void (async () => {
      try {
        const response = await fetchTranslationPreview(normalized, languageHint);
        translationCache.set(cacheKey, response.translated_text);
        if (!cancelled) {
          setTranslation(response.translated_text);
          setResolvedKey(cacheKey);
        }
      } catch {
        translationCache.set(cacheKey, null);
        if (!cancelled) {
          setTranslation(null);
          setResolvedKey(cacheKey);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [cacheKey, cachedTranslation, languageHint, locale, normalized]);

  const effectiveTranslation = cachedTranslation !== undefined
    ? cachedTranslation
    : resolvedKey === cacheKey
      ? translation
      : null;
  return <>{effectiveTranslation ?? text}</>;
}

function StatusPill({
  label,
  value,
  toneClass = "bg-[rgba(247,242,232,0.72)] text-[var(--ink)]",
}: {
  label: string;
  value: string;
  toneClass?: string;
}) {
  return (
    <span className={`rounded-full px-3 py-1 text-[11px] font-semibold ${toneClass}`}>
      <span className="text-[0.7rem] uppercase tracking-[0.14em] opacity-70">{label}: </span>
      <span>{value}</span>
    </span>
  );
}

function SegmentCluster({
  title,
  segments,
  activeSegment,
  locale,
  onSelect,
}: {
  title: string;
  segments: SegmentReport[];
  activeSegment: string | null;
  locale: Locale;
  onSelect: (segment: string) => void;
}) {
  return (
    <div>
      <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--muted)]">
        {title}
      </p>
      <div className="mt-3 grid gap-2">
        {segments.map((segment) => {
          const isActive = activeSegment === segment.segment;
          return (
            <button
              key={segment.segment}
              type="button"
              onClick={() => onSelect(segment.segment)}
              className={`rounded-[18px] border px-4 py-3 text-left transition ${
                isActive
                  ? "border-[var(--accent)] bg-[rgba(220,105,31,0.10)]"
                  : "border-black/[0.06] bg-[rgba(247,242,232,0.45)] hover:border-[var(--ink)]"
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-[var(--ink)]">{formatSegmentLabel(segment.segment, locale)}</p>
                </div>
                <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--ink)]">
                  {segment.item_count}
                </span>
              </div>
              <div className="mt-3 border-t border-black/[0.06] pt-2.5">
                <div className="flex items-center gap-2 overflow-hidden text-[9px] uppercase tracking-[0.12em] text-[var(--muted)]">
                  <span
                    className={`shrink-0 rounded-full px-2.5 py-1 text-[9px] font-semibold uppercase tracking-[0.14em] ${complementarityTone(
                      segment.complementarity,
                    )}`}
                  >
                    {formatComplementarity(segment.complementarity, locale)}
                  </span>
                  <span className="truncate whitespace-nowrap">
                    {segment.source_count} {locale === "ru" ? "ист." : "src"} · {segment.item_count} {locale === "ru" ? "мат." : "itm"}
                  </span>
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function TopicArticleAccordion({
  locale,
  topicGroup,
  defaultOpen = false,
}: {
  locale: Locale;
  topicGroup: SegmentTopicGroup;
  defaultOpen?: boolean;
}) {
  const t = COPY[locale];
  const [isOpen, setIsOpen] = useState(defaultOpen);
  return (
    <div className="rounded-[18px] border border-black/[0.06] bg-[rgba(247,242,232,0.45)] p-4">
      <button
        type="button"
        onClick={() => setIsOpen((current) => !current)}
        className="flex w-full cursor-pointer flex-wrap items-start justify-between gap-3 text-left"
      >
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h4 className="text-lg font-semibold text-[var(--ink)]">
              {formatNarrativeLabel(topicGroup.topic, locale)}
            </h4>
            <StatusPill
              label={t.labelTone}
              value={formatEmotion(topicGroup.dominantEmotion, locale)}
              toneClass={emotionTone(topicGroup.dominantEmotion)}
            />
            <StatusPill
              label={t.labelStance}
              value={formatStance(topicGroup.dominantStance, locale)}
              toneClass={stanceTone(topicGroup.dominantStance)}
            />
          </div>
          <p className="mt-3 text-sm leading-6 text-[var(--muted)]">
            <AutoTranslatedText text={topicGroup.summary} locale={locale} />
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <span className="rounded-full bg-[rgba(19,38,66,0.08)] px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-[var(--ink)]">
            {topicGroup.mentions}/{topicGroup.totalInSegment} {t.topicMentions}
          </span>
          <span className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-black/10 bg-white text-[var(--ink)]">
            <ChevronIcon open={isOpen} />
          </span>
        </div>
      </button>

      <AnimatedCollapse open={isOpen}>
        <div className="grid gap-4">
        <div className="flex flex-wrap gap-2">
          <span className="rounded-full bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--ink)]">
            {topicGroup.items.length} {t.items}
          </span>
          <span className="rounded-full bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">
            {topicGroup.sourceCount} {t.sourceCountShort}
          </span>
          <span className="rounded-full bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">
            {topicGroup.countryCount} {t.countryCountShort}
          </span>
          {topicGroup.accents.map((accent) => (
            <span
              key={`${topicGroup.topic}-${accent}`}
              className="rounded-full bg-[rgba(247,242,232,0.92)] px-3 py-2 text-xs leading-5 text-[var(--muted)]"
            >
              {accent}
            </span>
          ))}
        </div>

        <div className="grid gap-3">
          {topicGroup.items.map((item) => (
            <TopicArticleItem key={item.id} item={item} locale={locale} emphasis={topicGroup.topic} />
          ))}
        </div>
        </div>
      </AnimatedCollapse>
    </div>
  );
}

function TopicArticleItem({
  item,
  locale,
  emphasis,
}: {
  item: SearchItem;
  locale: Locale;
  emphasis?: string;
}) {
  const t = COPY[locale];
  const quote = bestQuoteOrExcerpt(item, emphasis);

  return (
    <article className="rounded-[18px] border border-black/[0.06] bg-white p-4">
      <a
        href={item.url}
        target="_blank"
        rel="noreferrer"
        className="block text-base font-semibold leading-7 text-[var(--ink)] underline-offset-4 hover:underline"
        title={t.openArticle}
      >
        <HoverTranslateText text={item.title} locale={locale} languageHint={item.language} />
      </a>

      <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] uppercase tracking-[0.16em] text-[var(--muted)]">
        <span className="font-semibold text-[var(--ink)]">{item.source_name}</span>
        <span>•</span>
        <span>{formatCountryLabel(item.source_country, locale)}</span>
        <span>•</span>
        <span>{formatDate(item.published_at, locale)}</span>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <StatusPill label={t.labelTone} value={formatEmotion(item.emotion, locale)} toneClass={emotionTone(item.emotion)} />
        <StatusPill label={t.labelStance} value={formatStance(item.stance, locale)} toneClass={stanceTone(item.stance)} />
        <StatusPill
          label={t.labelAlignment}
          value={formatAlignment(item.query_alignment, locale)}
          toneClass={alignmentTone(item.query_alignment)}
        />
        <StatusPill
          label={t.labelOriginality}
          value={formatOriginality(item.originality, locale)}
          toneClass={originalityTone(item.originality)}
        />
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <StatusPill label={t.labelTopic} value={formatNarrativeLabel(item.cluster_label ?? item.narrative, locale)} />
        <StatusPill label={t.labelSourceType} value={formatSourceTypeLabel(item.source_type, locale)} />
      </div>

      <div className="mt-4 rounded-[16px] bg-[rgba(247,242,232,0.42)] px-4 py-3">
        <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--muted)]">
          {t.articleSummary}
        </p>
        <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
          <AutoTranslatedText text={item.pivot_summary} locale={locale} languageHint={item.pivot_language ?? item.language} />
        </p>
      </div>

      {quote ? (
        <div className="mt-4 rounded-[16px] bg-[rgba(247,242,232,0.58)] px-4 py-3">
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--muted)]">
            {t.quoteOrExcerpt}
          </p>
          <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
            “<HoverTranslateText text={quote} locale={locale} languageHint={item.language} />”
          </p>
        </div>
      ) : null}
    </article>
  );
}

function QuoteItem({
  quote,
  locale,
}: {
  quote: {
    quote: string;
    source_name: string;
    topic: string;
    emotion: string;
    language?: string | null;
    url?: string | null;
    source_type?: string | null;
    stance?: string | null;
    query_alignment?: string | null;
    originality?: string | null;
  };
  locale: Locale;
}) {
  const t = COPY[locale];
  return (
    <div className="rounded-[16px] border border-black/[0.06] bg-white px-4 py-3">
      <div className="flex flex-wrap gap-2 border-b border-black/[0.06] pb-3">
        <StatusPill label={t.labelTopic} value={formatNarrativeLabel(quote.topic, locale)} />
        <StatusPill label={t.labelTone} value={formatEmotion(quote.emotion, locale)} toneClass={emotionTone(quote.emotion)} />
        {quote.stance ? (
          <StatusPill label={t.labelStance} value={formatStance(quote.stance, locale)} toneClass={stanceTone(quote.stance)} />
        ) : null}
        {quote.query_alignment ? (
          <StatusPill
            label={t.labelAlignment}
            value={formatAlignment(quote.query_alignment, locale)}
            toneClass={alignmentTone(quote.query_alignment)}
          />
        ) : null}
        {quote.originality ? (
          <StatusPill
            label={t.labelOriginality}
            value={formatOriginality(quote.originality, locale)}
            toneClass={originalityTone(quote.originality)}
          />
        ) : null}
        {quote.source_type ? (
          <StatusPill label={t.labelSourceType} value={formatSourceTypeLabel(quote.source_type, locale)} />
        ) : null}
      </div>
      <p className="mt-3 text-sm leading-6 text-[var(--muted)]">
        “<HoverTranslateText text={quote.quote} locale={locale} languageHint={quote.language} />”
      </p>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        {quote.url ? (
          <a
            href={quote.url}
            target="_blank"
            rel="noreferrer"
            className="text-sm font-semibold text-[var(--ink)] underline-offset-4 hover:underline"
          >
            {quote.source_name}
          </a>
        ) : (
          <span className="text-sm font-semibold text-[var(--ink)]">{quote.source_name}</span>
        )}
        <span className="text-xs uppercase tracking-[0.16em] text-[var(--muted)]">
          {quote.url ? t.openArticle : ""}
        </span>
      </div>
    </div>
  );
}

function NarrativeModal({
  locale,
  narrative,
  items,
  onClose,
}: {
  locale: Locale;
  narrative: { narrative: string; emotion: string };
  items: SearchItem[];
  onClose: () => void;
}) {
  const t = COPY[locale];

  return (
    <div
      className="fixed inset-0 z-[520] flex items-start justify-center bg-[rgba(19,38,66,0.28)] p-4 pt-20 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-[980px] rounded-[28px] border border-white/60 bg-[var(--paper)] p-5 shadow-[0_32px_90px_rgba(23,38,67,0.24)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[var(--muted)]">
              {t.narrativeFocus}
            </p>
            <h3 className="mt-3 font-display text-[30px] leading-[1.02] tracking-[-0.04em] text-[var(--ink)]">
              {formatNarrativeLabel(narrative.narrative, locale)}
            </h3>
            <div className="mt-3 flex flex-wrap gap-2">
              <StatusPill
                label={t.labelTone}
                value={formatEmotion(narrative.emotion, locale)}
                toneClass={emotionTone(narrative.emotion)}
              />
              <StatusPill label={t.narrativeMaterials} value={`${items.length}`} />
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            title={COPY[locale].closeModal}
            aria-label={COPY[locale].closeModal}
            className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-black/10 text-[var(--ink)] transition hover:bg-[var(--ink)] hover:text-white"
          >
            <CloseIcon />
          </button>
        </div>
        <div className="mt-5 max-h-[70vh] overflow-auto pr-1">
          <div className="grid gap-3">
            {items.length ? (
              items.map((item) => (
                <TopicArticleItem
                  key={`narrative-${item.id}`}
                  item={item}
                  locale={locale}
                  emphasis={narrative.narrative}
                />
              ))
            ) : (
              <EmptyPanel copy={t.noSignal} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function HoverTranslateText({
  text,
  locale,
  languageHint,
}: {
  text: string;
  locale: Locale;
  languageHint?: string | null;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [translation, setTranslation] = useState<string | null>(null);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) {
        window.clearTimeout(timerRef.current);
      }
    };
  }, []);

  if (!shouldOfferTranslation(text, locale, languageHint)) {
    return <>{text}</>;
  }

  const cacheKey = `${languageHint ?? "auto"}::${text}`;

  const handleEnter = () => {
    if (timerRef.current) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    const cached = translationCache.get(cacheKey);
    if (cached !== undefined) {
      setTranslation(cached);
      setIsOpen(true);
      return;
    }
    timerRef.current = window.setTimeout(async () => {
      setIsLoading(true);
      try {
        const response = await fetchTranslationPreview(text, languageHint);
        translationCache.set(cacheKey, response.translated_text);
        setTranslation(response.translated_text);
        setIsOpen(true);
      } catch {
        translationCache.set(cacheKey, null);
        setTranslation(null);
        setIsOpen(true);
      } finally {
        setIsLoading(false);
        timerRef.current = null;
      }
    }, 3000);
  };

  const handleLeave = () => {
    if (timerRef.current) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    setIsOpen(false);
    setIsLoading(false);
  };

  return (
    <span className="relative inline" onMouseEnter={handleEnter} onMouseLeave={handleLeave}>
      <span className="cursor-help decoration-dotted underline-offset-4 hover:underline">{text}</span>
      {(isOpen || isLoading) ? (
        <span className="pointer-events-none absolute bottom-full left-0 z-[140] mb-2 block w-[320px] max-w-[80vw] rounded-[16px] border border-black/10 bg-[var(--ink)] px-3 py-2 text-xs leading-5 text-white shadow-[0_18px_45px_rgba(23,38,67,0.22)]">
          {isLoading ? COPY[locale].translationLoading : translation ?? COPY[locale].translationUnavailable}
        </span>
      ) : null}
    </span>
  );
}

function SnapshotModal({
  locale,
  title,
  snapshots,
  activeSnapshotId,
  loadingSnapshotId,
  onClose,
  onOpenSnapshot,
}: {
  locale: Locale;
  title: string;
  snapshots: SnapshotSummary[];
  activeSnapshotId: string | null;
  loadingSnapshotId: string | null;
  onClose: () => void;
  onOpenSnapshot: (snapshotId: string) => void;
}) {
  return (
    <div
      className="fixed inset-0 z-[520] flex items-start justify-center bg-[rgba(19,38,66,0.28)] p-4 pt-20 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-[760px] rounded-[28px] border border-white/60 bg-[var(--paper)] p-5 shadow-[0_32px_90px_rgba(23,38,67,0.24)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[var(--muted)]">
            {title}
          </p>
          <button
            type="button"
            onClick={onClose}
            title={COPY[locale].closeModal}
            aria-label={COPY[locale].closeModal}
            className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-black/10 text-[var(--ink)] transition hover:bg-[var(--ink)] hover:text-white"
          >
            <CloseIcon />
          </button>
        </div>
        <div className="mt-4 grid max-h-[70vh] gap-3 overflow-auto pr-1">
          {snapshots.map((snapshot) => {
            const active = activeSnapshotId === snapshot.id;
            return (
              <button
                key={snapshot.id}
                type="button"
                onClick={() => onOpenSnapshot(snapshot.id)}
                className={`rounded-[20px] border p-4 text-left transition ${
                  active
                    ? "border-[var(--accent)] bg-[rgba(220,105,31,0.10)]"
                    : "border-black/[0.06] bg-white hover:border-[var(--ink)]"
                }`}
              >
                <div className="flex items-center justify-between gap-4">
                  <p className="line-clamp-2 font-semibold leading-6">{snapshot.query_text}</p>
                  {loadingSnapshotId === snapshot.id ? (
                    <span className="text-xs uppercase tracking-[0.18em] text-[var(--muted)]">
                      {COPY[locale].loading}
                    </span>
                  ) : null}
                </div>
                <div className="mt-3 flex flex-wrap gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-[var(--muted)]">
                  <span>
                    {snapshot.lookback_days}
                    {COPY[locale].daysShort}
                  </span>
                  <span>
                    {snapshot.total_results} {COPY[locale].items}
                  </span>
                  <span>{formatDate(snapshot.created_at, locale)}</span>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function ProviderStatusModal({
  locale,
  title,
  statuses,
  onClose,
}: {
  locale: Locale;
  title: string;
  statuses: ProviderStatus[];
  onClose: () => void;
}) {
  const readyCount = statuses.filter((row) => row.status === "ready" || row.status === "ok").length;
  const t = COPY[locale];

  return (
    <div
      className="fixed inset-0 z-[520] flex items-start justify-center bg-[rgba(19,38,66,0.28)] p-4 pt-20 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-[760px] rounded-[28px] border border-white/60 bg-[var(--paper)] p-5 shadow-[0_32px_90px_rgba(23,38,67,0.24)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[var(--muted)]">
              {title}
            </p>
            <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
              {t.providerReadiness}: {readyCount}/{statuses.length} {t.readyShort}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            title={COPY[locale].closeModal}
            aria-label={COPY[locale].closeModal}
            className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-black/10 text-[var(--ink)] transition hover:bg-[var(--ink)] hover:text-white"
          >
            <CloseIcon />
          </button>
        </div>
        <div className="mt-4 grid max-h-[70vh] gap-3 overflow-auto pr-1">
          {statuses.length ? (
            statuses.map((row) => (
              <div
                key={`${row.provider}-${row.status}-${row.count}`}
                className="rounded-[20px] border border-black/[0.06] bg-white p-4"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-[var(--ink)]">
                      {capitalizeFirst(formatProviderName(row.provider))}
                    </p>
                    {row.message ? (
                      <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
                        {cleanCoverageGapText(row.message)}
                      </p>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] ${statusTone(row.status)}`}>
                      {formatStatus(row.status, locale)}
                    </span>
                    <span className="rounded-full bg-[rgba(19,38,66,0.08)] px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--ink)]">
                      {row.count} {t.items}
                    </span>
                  </div>
                </div>
              </div>
            ))
          ) : (
            <EmptyPanel copy={t.noSignal} />
          )}
        </div>
      </div>
    </div>
  );
}
