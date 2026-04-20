"use client";

import { FormEvent, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { motion } from "framer-motion";

import { analyzeEventRegistryNarratives, ApiError, searchEventRegistryNews } from "@/lib/api";
import { COUNTRY_OPTIONS } from "@/lib/countries";
import type {
  EventRegistryArticle,
  EventRegistryNarrative,
  EventRegistryNarrativesResponse,
  EventRegistrySearchResponse,
} from "@/lib/types";

type DisplaySortMode =
  | "country"
  | "source"
  | "date_desc"
  | "date_asc"
  | "relevance"
  | "tone_desc"
  | "tone_asc"
  | "narrative_forward"
  | "narrative_reverse";
type CardsPerRow = 4 | 6 | 8;
type FilterDropdown = "sources" | "countries" | "languages";
type TimelinePoint = {
  dateKey: string;
  count: number;
};

type TimelineSeries = {
  narrative: string;
  stance: EventRegistryNarrative["stance"];
  totalCount: number;
  points: TimelinePoint[];
};

type ArticleMeta = {
  title: string;
  sourceName: string;
  language: string | null;
  publishedAt: string;
};

type ResearchSnapshot = {
  id: string;
  savedAt: string;
  query: string;
  lookbackDays: number;
  limit: number;
  sortBy: DisplaySortMode;
  result: EventRegistrySearchResponse;
  narrativesResult: EventRegistryNarrativesResponse | null;
};

const LOOKBACK_OPTIONS = [
  { value: 1, label: "1 день" },
  { value: 7, label: "7 дней" },
  { value: 30, label: "30 дней" },
  { value: 60, label: "60 дней" },
  { value: 90, label: "90 дней" },
  { value: 180, label: "180 дней" },
  { value: 360, label: "360 дней" },
] as const;

const LIMIT_OPTIONS = [
  { value: 10, label: "10 статей" },
  { value: 25, label: "25 статей" },
  { value: 50, label: "50 статей" },
  { value: 100, label: "100 статей" },
  { value: 200, label: "200 статей" },
] as const;

const DISPLAY_SORT_OPTIONS = [
  { value: "relevance", label: "По релевантности" },
  { value: "country", label: "По стране" },
  { value: "source", label: "По источнику" },
  { value: "date_desc", label: "Новые -> старые" },
  { value: "date_asc", label: "Старые -> новые" },
  { value: "tone_desc", label: "Тон: позитив -> негатив" },
  { value: "tone_asc", label: "Тон: негатив -> позитив" },
  { value: "narrative_forward", label: "Подача: поддержка -> оспаривание" },
  { value: "narrative_reverse", label: "Подача: оспаривание -> поддержка" },
] as const satisfies ReadonlyArray<{ value: DisplaySortMode; label: string }>;

const CARDS_PER_ROW_OPTIONS = [
  { value: 4, label: "4 в ряд" },
  { value: 6, label: "6 в ряд" },
  { value: 8, label: "8 в ряд" },
] as const satisfies ReadonlyArray<{ value: CardsPerRow; label: string }>;

const GRID_COLUMNS_CLASSNAME: Record<CardsPerRow, string> = {
  4: "grid-cols-1 sm:grid-cols-2 xl:grid-cols-4",
  6: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-6",
  8: "grid-cols-1 sm:grid-cols-2 md:grid-cols-4 2xl:grid-cols-8",
};

const CARD_IMAGE_HEIGHT_CLASSNAME: Record<CardsPerRow, string> = {
  4: "h-32",
  6: "h-24",
  8: "h-20",
};

const CARD_TITLE_CLASSNAME: Record<CardsPerRow, string> = {
  4: "text-[1.02rem]",
  6: "text-[0.94rem]",
  8: "text-[0.88rem]",
};

const CARD_SOURCE_CLASSNAME: Record<CardsPerRow, string> = {
  4: "text-sm",
  6: "text-[12px]",
  8: "text-[11px]",
};

const COUNTRY_LABELS = new Map(
  COUNTRY_OPTIONS.map((option) => [option.code, option.label.ru]),
);

const LANGUAGE_CODE_ALIASES: Record<string, string> = {
  ara: "ar",
  ar: "ar",
  deu: "de",
  de: "de",
  eng: "en",
  en: "en",
  fas: "fa",
  fa: "fa",
  fra: "fr",
  fr: "fr",
  hin: "hi",
  hi: "hi",
  ita: "it",
  it: "it",
  jpn: "ja",
  ja: "ja",
  kor: "ko",
  ko: "ko",
  por: "pt",
  pt: "pt",
  rus: "ru",
  ru: "ru",
  spa: "es",
  es: "es",
  tur: "tr",
  tr: "tr",
  zho: "zh",
  zh: "zh",
};

const SNAPSHOTS_STORAGE_KEY = "event-registry-research-snapshots-v1";
const MAX_SNAPSHOTS = 25;

function readErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Не удалось выполнить поиск.";
}

function getProgressValue(isLoading: boolean, elapsedSeconds: number, hasResult: boolean): number {
  if (hasResult && !isLoading) {
    return 100;
  }
  if (!isLoading) {
    return 0;
  }
  const eased = 1 - Math.exp(-elapsedSeconds / 5);
  return Math.min(88, Math.round(18 + eased * 70));
}

function formatPublishedAt(value: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function capitalizeFirst(value: string): string {
  if (!value) {
    return value;
  }
  return value[0].toUpperCase() + value.slice(1);
}

function formatLanguage(value: string | null): string {
  if (!value) {
    return "n/a";
  }
  const normalized = LANGUAGE_CODE_ALIASES[value.toLowerCase()] ?? value.toLowerCase();
  const displayName = new Intl.DisplayNames(["ru-RU"], { type: "language" }).of(normalized);
  return capitalizeFirst(displayName ?? value.toUpperCase());
}

function formatCountry(value: string | null): string {
  if (!value) {
    return "Неизвестно";
  }
  const normalized = value.toUpperCase();
  if (COUNTRY_LABELS.has(normalized)) {
    return COUNTRY_LABELS.get(normalized) ?? normalized;
  }
  const displayName = new Intl.DisplayNames(["ru-RU"], { type: "region" }).of(normalized);
  return displayName ?? normalized;
}

function formatSocialScore(value: number): string {
  if (value >= 1000) {
    return `${(value / 1000).toFixed(1)}k`;
  }
  return value.toFixed(0);
}

function isNumber(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function getSentimentChipStyle(value: number): CSSProperties {
  const clamped = Math.max(-100, Math.min(100, value));
  const intensity = Math.abs(clamped) / 100;

  if (intensity === 0) {
    return {
      borderColor: "rgba(19, 38, 66, 0.1)",
      backgroundColor: "#ffffff",
      color: "#5d6d83",
    };
  }

  const hue = clamped > 0 ? 145 : 6;
  const saturation = 28 + intensity * 44;
  const backgroundLightness = 97 - intensity * 12;
  const borderLightness = 88 - intensity * 24;
  const textLightness = 34 - intensity * 10;

  return {
    borderColor: `hsl(${hue}, ${Math.round(saturation)}%, ${Math.round(borderLightness)}%)`,
    backgroundColor: `hsl(${hue}, ${Math.round(saturation)}%, ${Math.round(backgroundLightness)}%)`,
    color: `hsl(${hue}, ${Math.round(saturation - 8)}%, ${Math.round(textLightness)}%)`,
  };
}

function getSocialChipClassName(value: number): string {
  if (value >= 1000) {
    return "border-orange-200 bg-orange-50 text-orange-800";
  }
  if (value >= 100) {
    return "border-amber-200 bg-amber-50 text-amber-800";
  }
  return "border-[#132642]/10 bg-white text-[#5d6d83]";
}

function formatNarrativeType(value: string | null): string {
  const map: Record<string, string> = {
    support: "Поддержка",
    dispute: "Оспаривание",
    analysis: "Разбор",
    mixed: "Смешанное",
  };
  if (!value) {
    return "Разбор";
  }
  return map[value] ?? value;
}

function getNarrativeChipClassName(value: string | null): string {
  if (value === "support") {
    return "border-emerald-200 bg-emerald-50 text-emerald-800";
  }
  if (value === "dispute") {
    return "border-rose-200 bg-rose-50 text-rose-800";
  }
  if (value === "mixed") {
    return "border-amber-200 bg-amber-50 text-amber-800";
  }
  return "border-sky-200 bg-sky-50 text-sky-800";
}

function getFilterTriggerClassName(isOpen: boolean): string {
  return [
    "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm font-bold transition outline-none",
    isOpen
      ? "border-[#dc691f]/35 bg-[#fff4eb] text-[#132642] shadow-[0_8px_24px_rgba(220,105,31,0.12)]"
      : "border-[#132642]/10 bg-white text-[#132642] hover:border-[#dc691f]/30 hover:bg-[#fffaf3]",
  ].join(" ");
}

function formatNarrativeStance(value: EventRegistryNarrative["stance"]): string {
  if (value === "support") {
    return "Поддерживающий";
  }
  if (value === "dispute") {
    return "Оспаривающий";
  }
  if (value === "mixed") {
    return "Смешанный";
  }
  return "Нейтральный";
}

function getNarrativeStanceClassName(value: EventRegistryNarrative["stance"]): string {
  if (value === "support") {
    return "border-emerald-200 bg-emerald-50 text-emerald-800";
  }
  if (value === "dispute") {
    return "border-rose-200 bg-rose-50 text-rose-800";
  }
  if (value === "mixed") {
    return "border-amber-200 bg-amber-50 text-amber-800";
  }
  return "border-sky-200 bg-sky-50 text-sky-800";
}

function formatTimelineDateLabel(dateKey: string): string {
  const date = new Date(`${dateKey}T00:00:00Z`);
  return new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "short" }).format(date);
}

function normalizeDateKey(value: string): string | null {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return date.toISOString().slice(0, 10);
}

function timelineColorByIndex(index: number): string {
  const hue = Math.round((index * 137.508) % 360);
  return `hsl(${hue}, 74%, 48%)`;
}

function compactResultForSnapshot(result: EventRegistrySearchResponse): EventRegistrySearchResponse {
  return {
    ...result,
    items: result.items.map((item) => ({
      ...item,
      full_text: null,
    })),
  };
}

function buildNarrativesCacheKey(
  query: string,
  items: Array<Pick<EventRegistryArticle, "url">>,
): string {
  const urls = items
    .map((item) => item.url.trim())
    .filter(Boolean)
    .sort((left, right) => left.localeCompare(right));
  return `${query.trim().toLowerCase()}::${urls.join("|")}`;
}

function sortArticles(items: EventRegistryArticle[], mode: DisplaySortMode): EventRegistryArticle[] {
  const nextItems = [...items];
  const narrativeRank: Record<string, number> = {
    support: 0,
    analysis: 1,
    mixed: 2,
    dispute: 3,
  };

  nextItems.sort((left, right) => {
    if (mode === "country") {
      const leftCountry = (left.source_country ?? "zzz").toLocaleLowerCase("ru-RU");
      const rightCountry = (right.source_country ?? "zzz").toLocaleLowerCase("ru-RU");
      const countryCompare = leftCountry.localeCompare(rightCountry, "ru-RU");
      if (countryCompare !== 0) {
        return countryCompare;
      }
      return left.source_name.localeCompare(right.source_name, "ru-RU");
    }

    if (mode === "source") {
      const sourceCompare = left.source_name.localeCompare(right.source_name, "ru-RU");
      if (sourceCompare !== 0) {
        return sourceCompare;
      }
      return left.title.localeCompare(right.title, "ru-RU");
    }

    if (mode === "date_desc") {
      return new Date(right.published_at).getTime() - new Date(left.published_at).getTime();
    }

    if (mode === "date_asc") {
      return new Date(left.published_at).getTime() - new Date(right.published_at).getTime();
    }

    if (mode === "tone_desc") {
      const leftTone = left.tone_score ?? -Infinity;
      const rightTone = right.tone_score ?? -Infinity;
      if (leftTone !== rightTone) {
        return rightTone - leftTone;
      }
      return new Date(right.published_at).getTime() - new Date(left.published_at).getTime();
    }

    if (mode === "tone_asc") {
      const leftTone = left.tone_score ?? Infinity;
      const rightTone = right.tone_score ?? Infinity;
      if (leftTone !== rightTone) {
        return leftTone - rightTone;
      }
      return new Date(right.published_at).getTime() - new Date(left.published_at).getTime();
    }

    if (mode === "narrative_forward") {
      const leftRank = narrativeRank[left.narrative_type ?? "analysis"] ?? 1;
      const rightRank = narrativeRank[right.narrative_type ?? "analysis"] ?? 1;
      if (leftRank !== rightRank) {
        return leftRank - rightRank;
      }
      return new Date(right.published_at).getTime() - new Date(left.published_at).getTime();
    }

    if (mode === "narrative_reverse") {
      const leftRank = narrativeRank[left.narrative_type ?? "analysis"] ?? 1;
      const rightRank = narrativeRank[right.narrative_type ?? "analysis"] ?? 1;
      if (leftRank !== rightRank) {
        return rightRank - leftRank;
      }
      return new Date(right.published_at).getTime() - new Date(left.published_at).getTime();
    }

    const leftScore = left.relevance_score ?? -Infinity;
    const rightScore = right.relevance_score ?? -Infinity;
    if (leftScore !== rightScore) {
      return rightScore - leftScore;
    }
    return new Date(right.published_at).getTime() - new Date(left.published_at).getTime();
  });

  return nextItems;
}

function StatChip({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full border border-[#132642]/10 bg-white px-3 py-1.5 text-sm font-bold text-[#132642]">
      {children}
    </span>
  );
}

function ArticleCard({
  article,
  cardsPerRow,
}: {
  article: EventRegistryArticle;
  cardsPerRow: CardsPerRow;
}) {
  const [imageFailed, setImageFailed] = useState(false);

  const showPlaceholder = !article.image_url || imageFailed;

  return (
    <article className="rounded-[1.15rem] border border-[#132642]/10 bg-[#fffdf9]/92 shadow-[0_12px_30px_rgba(19,38,66,0.05)]">
      {showPlaceholder ? (
        <div
          className={`overflow-hidden rounded-t-[1.15rem] bg-[linear-gradient(135deg,rgba(19,38,66,0.96),rgba(220,105,31,0.84))] ${CARD_IMAGE_HEIGHT_CLASSNAME[cardsPerRow]}`}
        >
          <div className="flex h-full w-full flex-col justify-between px-4 py-3 text-white">
            <span className="text-[10px] font-bold uppercase tracking-[0.24em] text-white/70">
              no image
            </span>
            <div className="space-y-1">
              <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-white/78">
                {article.source_name}
              </p>
              <p className="line-clamp-2 text-sm font-semibold leading-tight text-white">
                {article.title}
              </p>
            </div>
          </div>
        </div>
      ) : (
        <div
          className={`overflow-hidden rounded-t-[1.15rem] bg-[#132642]/6 ${CARD_IMAGE_HEIGHT_CLASSNAME[cardsPerRow]}`}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={article.image_url ?? undefined}
            alt=""
            className="h-full w-full object-cover"
            loading="lazy"
            decoding="async"
            referrerPolicy="no-referrer"
            onError={() => setImageFailed(true)}
          />
        </div>
      )}

      <div className="space-y-3 px-4 py-4">
        <div className="flex flex-wrap items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.14em] text-[#8090a3]">
          <span>{article.domain}</span>
          <span className="h-1 w-1 rounded-full bg-[#132642]/25" />
          <span>{formatPublishedAt(article.published_at)}</span>
          <span className="h-1 w-1 rounded-full bg-[#132642]/25" />
          <span>{formatLanguage(article.language)}</span>
          {article.source_country ? (
            <>
              <span className="h-1 w-1 rounded-full bg-[#132642]/25" />
              <span>{formatCountry(article.source_country)}</span>
            </>
          ) : null}
        </div>

        <div className="space-y-2">
          <p className={`font-bold uppercase tracking-[0.18em] text-[#dc691f] ${CARD_SOURCE_CLASSNAME[cardsPerRow]}`}>
            {article.source_name}
          </p>
          <a
            href={article.url}
            target="_blank"
            rel="noreferrer"
            className={`block font-display leading-[1.15] text-[#132642] transition hover:text-[#dc691f] ${CARD_TITLE_CLASSNAME[cardsPerRow]}`}
          >
            {article.title}
          </a>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs text-[#5d6d83]">
          {isNumber(article.relevance_score) ? (
            <span className="rounded-full border border-[#132642]/10 bg-white px-3 py-1.5 text-[#132642]">
              Релевантность: {article.relevance_score.toFixed(0)}
            </span>
          ) : null}
          {isNumber(article.tone_score) ? (
            <span
              className="rounded-full border px-3 py-1.5"
              style={getSentimentChipStyle(article.tone_score)}
            >
              Эмоц. окраска: {article.tone_score > 0 ? "+" : ""}{article.tone_score}
            </span>
          ) : null}
          {article.narrative_type ? (
            <span className={`rounded-full border px-3 py-1.5 ${getNarrativeChipClassName(article.narrative_type)}`}>
              Подача: {formatNarrativeType(article.narrative_type)}
            </span>
          ) : null}
          {isNumber(article.social_score) ? (
            <span className={`rounded-full border px-3 py-1.5 ${getSocialChipClassName(article.social_score)}`}>
              Резонанс {formatSocialScore(article.social_score)}
            </span>
          ) : null}
        </div>
      </div>
    </article>
  );
}

export function EventRegistryDashboard() {
  const [query, setQuery] = useState("");
  const [lookbackDays, setLookbackDays] = useState(30);
  const [limit, setLimit] = useState(25);
  const [sortBy, setSortBy] = useState<DisplaySortMode>("relevance");
  const [cardsPerRow, setCardsPerRow] = useState<CardsPerRow>(4);
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [selectedCountries, setSelectedCountries] = useState<string[]>([]);
  const [selectedLanguages, setSelectedLanguages] = useState<string[]>([]);
  const [result, setResult] = useState<EventRegistrySearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [openDropdown, setOpenDropdown] = useState<FilterDropdown | null>(null);
  const [isNarrativesModalOpen, setIsNarrativesModalOpen] = useState(false);
  const [isNarrativesLoading, setIsNarrativesLoading] = useState(false);
  const [narrativesResult, setNarrativesResult] = useState<EventRegistryNarrativesResponse | null>(null);
  const [narrativesCacheKey, setNarrativesCacheKey] = useState<string | null>(null);
  const [narrativesError, setNarrativesError] = useState<string | null>(null);
  const [expandedNarratives, setExpandedNarratives] = useState<string[]>([]);
  const [isTimelineModalOpen, setIsTimelineModalOpen] = useState(false);
  const [selectedTimelineNarratives, setSelectedTimelineNarratives] = useState<string[]>([]);
  const [snapshots, setSnapshots] = useState<ResearchSnapshot[]>([]);
  const [isSnapshotsModalOpen, setIsSnapshotsModalOpen] = useState(false);
  const [activeSnapshotId, setActiveSnapshotId] = useState<string | null>(null);
  const filterDropdownsRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!startedAt) {
      setElapsedSeconds(0);
      return;
    }

    if (!isLoading) {
      setElapsedSeconds(Math.max(0, Math.floor((Date.now() - startedAt) / 1000)));
      return;
    }

    const timer = window.setInterval(() => {
      setElapsedSeconds(Math.max(0, Math.floor((Date.now() - startedAt) / 1000)));
    }, 1000);

    return () => window.clearInterval(timer);
  }, [isLoading, startedAt]);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(SNAPSHOTS_STORAGE_KEY);
      if (!raw) {
        return;
      }
      const parsed = JSON.parse(raw) as ResearchSnapshot[];
      if (!Array.isArray(parsed)) {
        return;
      }
      setSnapshots(parsed);
    } catch {}
  }, []);

  useEffect(() => {
    function handlePointerDown(event: PointerEvent) {
      if (!filterDropdownsRef.current) {
        return;
      }
      if (!(event.target instanceof Node)) {
        return;
      }
      if (!filterDropdownsRef.current.contains(event.target)) {
        setOpenDropdown(null);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpenDropdown(null);
      }
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

  const progressValue = useMemo(
    () => getProgressValue(isLoading, elapsedSeconds, Boolean(result)),
    [elapsedSeconds, isLoading, result],
  );
  const coverage = result?.coverage;
  const availableCountries = useMemo(
    () => coverage?.countries ?? [],
    [coverage?.countries],
  );
  const availableCountryOptions = useMemo(
    () =>
      availableCountries
        .map((country) => ({
          code: country,
          label: formatCountry(country),
        }))
        .sort((left, right) => left.label.localeCompare(right.label, "ru-RU")),
    [availableCountries],
  );
  const availableSourceOptions = useMemo(
    () =>
      Array.from(new Set((result?.items ?? []).map((item) => item.source_name)))
        .filter(Boolean)
        .sort((left, right) => left.localeCompare(right, "ru-RU")),
    [result?.items],
  );
  const availableLanguageOptions = useMemo(
    () =>
      (coverage?.languages ?? [])
        .map((language) => ({
          code: language,
          label: formatLanguage(language),
        }))
        .sort((left, right) => left.label.localeCompare(right.label, "ru-RU")),
    [coverage?.languages],
  );
  const visibleItems = useMemo(() => {
    const items = result?.items ?? [];
    const filteredItems = items.filter((item) => {
      if (selectedSources.length && !selectedSources.includes(item.source_name)) {
        return false;
      }
      if (selectedCountries.length && (!item.source_country || !selectedCountries.includes(item.source_country))) {
        return false;
      }
      if (selectedLanguages.length && (!item.language || !selectedLanguages.includes(item.language))) {
        return false;
      }
      return true;
    });
    return sortArticles(filteredItems, sortBy);
  }, [result?.items, selectedSources, selectedCountries, selectedLanguages, sortBy]);
  const articleMetaByUrl = useMemo(() => {
    const map = new Map<string, ArticleMeta>();
    for (const item of result?.items ?? []) {
      map.set(item.url, {
        title: item.title,
        sourceName: item.source_name,
        publishedAt: item.published_at,
        language: item.language,
      });
    }
    return map;
  }, [result?.items]);
  const narrativeTimelineSeries = useMemo<TimelineSeries[]>(() => {
    if (!narrativesResult) {
      return [];
    }
    const series: TimelineSeries[] = [];
    for (const narrative of narrativesResult.narratives) {
      const counters = new Map<string, number>();
      const candidateUrls = narrative.article_urls.length
        ? narrative.article_urls
        : narrative.evidences.map((evidence) => evidence.article_url);
      for (const url of candidateUrls) {
        const publishedAt = articleMetaByUrl.get(url)?.publishedAt;
        if (!publishedAt) {
          continue;
        }
        const dateKey = normalizeDateKey(publishedAt);
        if (!dateKey) {
          continue;
        }
        counters.set(dateKey, (counters.get(dateKey) ?? 0) + 1);
      }
      const points = Array.from(counters.entries())
        .map(([dateKey, count]) => ({ dateKey, count }))
        .sort((left, right) => left.dateKey.localeCompare(right.dateKey));
      series.push({
        narrative: narrative.narrative,
        stance: narrative.stance,
        totalCount: narrative.article_count,
        points,
      });
    }
    return series
      .filter((item) => item.points.length > 0)
      .sort((left, right) => right.totalCount - left.totalCount);
  }, [articleMetaByUrl, narrativesResult]);
  const selectedTimelineSeries = useMemo(
    () =>
      narrativeTimelineSeries.filter((series) =>
        selectedTimelineNarratives.includes(series.narrative),
      ),
    [narrativeTimelineSeries, selectedTimelineNarratives],
  );
  const timelineDateKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const series of selectedTimelineSeries) {
      for (const point of series.points) {
        keys.add(point.dateKey);
      }
    }
    return Array.from(keys).sort((left, right) => left.localeCompare(right));
  }, [selectedTimelineSeries]);
  const timelineMaxCount = useMemo(() => {
    const values = selectedTimelineSeries.flatMap((series) => series.points.map((point) => point.count));
    return values.length ? Math.max(...values) : 1;
  }, [selectedTimelineSeries]);
  const timelineColorMap = useMemo(() => {
    const map = new Map<string, string>();
    narrativeTimelineSeries.forEach((series, index) => {
      map.set(series.narrative, timelineColorByIndex(index));
    });
    return map;
  }, [narrativeTimelineSeries]);
  const currentNarrativesCacheKey = useMemo(
    () => (result ? buildNarrativesCacheKey(result.query, result.items) : null),
    [result],
  );
  const backendSortMode =
    sortBy === "date_asc" || sortBy === "date_desc" ? "date" : "relevance";

  useEffect(() => {
    setSelectedCountries((current) =>
      current.filter((country) => availableCountries.includes(country)),
    );
  }, [availableCountries]);

  useEffect(() => {
    setSelectedSources((current) =>
      current.filter((source) => availableSourceOptions.includes(source)),
    );
  }, [availableSourceOptions]);

  useEffect(() => {
    setSelectedLanguages((current) =>
      current.filter((language) => availableLanguageOptions.some((item) => item.code === language)),
    );
  }, [availableLanguageOptions]);

  useEffect(() => {
    setSelectedTimelineNarratives((current) => {
      const available = narrativeTimelineSeries.map((series) => series.narrative);
      const persisted = current.filter((name) => available.includes(name));
      if (persisted.length > 0) {
        return persisted;
      }
      return available.slice(0, 4);
    });
  }, [narrativeTimelineSeries]);

  function persistSnapshots(nextSnapshots: ResearchSnapshot[]) {
    setSnapshots(nextSnapshots);
    try {
      window.localStorage.setItem(SNAPSHOTS_STORAGE_KEY, JSON.stringify(nextSnapshots));
    } catch {}
  }

  function saveSnapshot(
    payload: {
      query: string;
      lookbackDays: number;
      limit: number;
      sortBy: DisplaySortMode;
      result: EventRegistrySearchResponse;
      narrativesResult: EventRegistryNarrativesResponse | null;
    },
    snapshotId?: string,
  ) {
    const nextId = snapshotId ?? `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const nextSnapshot: ResearchSnapshot = {
      id: nextId,
      savedAt: new Date().toISOString(),
      query: payload.query,
      lookbackDays: payload.lookbackDays,
      limit: payload.limit,
      sortBy: payload.sortBy,
      result: compactResultForSnapshot(payload.result),
      narrativesResult: payload.narrativesResult,
    };

    const withoutCurrent = snapshots.filter((item) => item.id !== nextId);
    const limited = [nextSnapshot, ...withoutCurrent].slice(0, MAX_SNAPSHOTS);
    persistSnapshots(limited);
    setActiveSnapshotId(nextId);
  }

  function openSnapshot(snapshot: ResearchSnapshot) {
    setActiveSnapshotId(snapshot.id);
    setQuery(snapshot.query);
    setLookbackDays(snapshot.lookbackDays);
    setLimit(snapshot.limit);
    setSortBy(snapshot.sortBy);
    setResult(snapshot.result);
    setNarrativesResult(snapshot.narrativesResult);
    setNarrativesCacheKey(
      snapshot.narrativesResult ? buildNarrativesCacheKey(snapshot.result.query, snapshot.result.items) : null,
    );
    setNarrativesError(snapshot.narrativesResult?.message ?? null);
    setExpandedNarratives(snapshot.narrativesResult?.narratives[0] ? [snapshot.narrativesResult.narratives[0].narrative] : []);
    setError(snapshot.result.status !== "ok" ? snapshot.result.message : null);
    setSelectedCountries([]);
    setSelectedSources([]);
    setSelectedLanguages([]);
    setIsSnapshotsModalOpen(false);
  }

  function deleteSnapshot(snapshotId: string) {
    const next = snapshots.filter((item) => item.id !== snapshotId);
    persistSnapshots(next);
    if (activeSnapshotId === snapshotId) {
      setActiveSnapshotId(null);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const nextQuery = query.trim();
    if (nextQuery.length < 3) {
      return;
    }

    setIsLoading(true);
    setError(null);
    setResult(null);
    setSelectedSources([]);
    setSelectedCountries([]);
    setSelectedLanguages([]);
    setOpenDropdown(null);
    setNarrativesResult(null);
    setNarrativesCacheKey(null);
    setNarrativesError(null);
    setExpandedNarratives([]);
    setSelectedTimelineNarratives([]);
    setIsNarrativesModalOpen(false);
    setIsTimelineModalOpen(false);
    setStartedAt(Date.now());
    setElapsedSeconds(0);

    try {
      const nextResult = await searchEventRegistryNews({
        query: nextQuery,
        lookback_days: lookbackDays,
        limit,
        sort_by: backendSortMode,
      });

      setResult(nextResult);
      setActiveSnapshotId(null);
      if (nextResult.status !== "ok") {
        setError(nextResult.message);
      }
      saveSnapshot(
        {
          query: nextQuery,
          lookbackDays,
          limit,
          sortBy,
          result: nextResult,
          narrativesResult: null,
        },
      );
    } catch (requestError) {
      setError(readErrorMessage(requestError));
    } finally {
      setIsLoading(false);
    }
  }

  async function handleNarrativesClick() {
    if (!result?.items.length || isNarrativesLoading) {
      return;
    }
    setIsNarrativesModalOpen(true);
    if (
      narrativesResult
      && currentNarrativesCacheKey
      && narrativesCacheKey === currentNarrativesCacheKey
      && !narrativesError
    ) {
      return;
    }
    setNarrativesError(null);
    setIsNarrativesLoading(true);
    try {
      const response = await analyzeEventRegistryNarratives({
        query: result.query,
        articles: result.items.map((article) => ({
          title: article.title,
          url: article.url,
          summary: article.summary,
          full_text: article.full_text,
          language: article.language,
          source_name: article.source_name,
          published_at: article.published_at,
          relevance_score: article.relevance_score,
        })),
      });
      setNarrativesResult(response);
      setNarrativesCacheKey(currentNarrativesCacheKey);
      if (response.message) {
        setNarrativesError(response.message);
      } else {
        setExpandedNarratives((response.narratives[0] ? [response.narratives[0].narrative] : []));
      }
      if (result) {
        saveSnapshot(
          {
            query: result.query,
            lookbackDays,
            limit,
            sortBy,
            result,
            narrativesResult: response,
          },
          activeSnapshotId ?? undefined,
        );
      }
    } catch (requestError) {
      setNarrativesError(readErrorMessage(requestError));
    } finally {
      setIsNarrativesLoading(false);
    }
  }

  return (
    <main className="relative flex min-h-screen flex-1 overflow-hidden px-4 py-8 sm:px-6 lg:px-8">
      <button
        type="button"
        onClick={() => setIsSnapshotsModalOpen(true)}
        className="fixed right-5 top-5 z-[60] inline-flex h-12 w-12 items-center justify-center rounded-full border border-[#132642]/18 bg-white/95 text-[#132642] shadow-[0_12px_28px_rgba(19,38,66,0.16)] backdrop-blur transition hover:border-[#1d4d7c]/35 hover:bg-[#f7fbff]"
        title={snapshots.length ? `Снимки (${snapshots.length})` : "Снимки пока пусты"}
        aria-label="Открыть снимки"
      >
        <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M6 4.5h8.8L18 7.7V19.5H6V4.5Z" />
          <path d="M14.8 4.5V8h3.2" />
          <path d="M8.5 11h7" />
          <path d="M8.5 14h7" />
          <path d="M8.5 17h5" />
        </svg>
      </button>
      <div className="pointer-events-none absolute inset-x-0 top-0 h-64 bg-[radial-gradient(circle_at_top,rgba(220,105,31,0.2),transparent_55%)]" />

      <div className="relative mx-auto flex w-full max-w-[1800px] flex-col gap-6">
        <section className="overflow-hidden rounded-[2rem] border border-[#132642]/12 bg-[#fffdf9]/92 px-4 py-5 shadow-[0_18px_60px_rgba(19,38,66,0.08)] backdrop-blur sm:px-6">
          <form onSubmit={handleSubmit} className="flex flex-col gap-3 lg:flex-row lg:items-center">
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Например: закрытие Ормузского пролива"
              className="min-w-0 flex-1 rounded-[1.35rem] border border-[#132642]/12 bg-white px-5 py-4 text-[15px] text-[#132642] shadow-[inset_0_1px_0_rgba(255,255,255,0.8)] outline-none transition placeholder:text-[#8090a3] focus:border-[#dc691f]/40 focus:ring-4 focus:ring-[#dc691f]/10"
            />

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-2 lg:w-auto">
              <select
                value={lookbackDays}
                onChange={(event) => setLookbackDays(Number(event.target.value))}
                className="rounded-[1.2rem] border border-[#132642]/12 bg-white px-4 py-4 text-sm font-bold text-[#132642] outline-none transition focus:border-[#dc691f]/40 focus:ring-4 focus:ring-[#dc691f]/10"
              >
                {LOOKBACK_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>

              <select
                value={limit}
                onChange={(event) => setLimit(Number(event.target.value))}
                className="rounded-[1.2rem] border border-[#132642]/12 bg-white px-4 py-4 text-sm font-bold text-[#132642] outline-none transition focus:border-[#dc691f]/40 focus:ring-4 focus:ring-[#dc691f]/10"
              >
                {LIMIT_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            <button
              type="submit"
              disabled={isLoading || query.trim().length < 3}
              className="inline-flex min-h-14 items-center justify-center rounded-[1.35rem] bg-[#132642] px-6 text-sm font-bold text-white transition hover:bg-[#0f2036] disabled:cursor-not-allowed disabled:bg-[#132642]/45 lg:px-7"
            >
              {isLoading ? "Ищем новости..." : "Найти новости"}
            </button>
          </form>
        </section>

        {isLoading ? (
          <section className="overflow-hidden rounded-full border border-[#132642]/10 bg-[#fffdf9]/88 px-1 py-1 shadow-[0_12px_30px_rgba(19,38,66,0.05)]">
            <div className="h-3 overflow-hidden rounded-full bg-[#132642]/8">
              <div
                className="research-progress relative h-full rounded-full bg-[linear-gradient(90deg,#132642_0%,#1d4d7c_55%,#dc691f_100%)] transition-[width] duration-700 ease-out"
                style={{ width: `${progressValue}%` }}
              />
            </div>
          </section>
        ) : null}

        {error ? (
          <section className="rounded-[1.8rem] border border-[#a61d24]/18 bg-[#fff6f6] px-5 py-4 text-[15px] leading-7 text-[#8d1d24] shadow-[0_14px_40px_rgba(141,29,36,0.08)]">
            {error}
          </section>
        ) : null}

        {coverage ? (
          <section className="flex flex-wrap items-center gap-2">
            <StatChip>Статей {coverage.total_results}</StatChip>
            <div ref={filterDropdownsRef} className="contents">
              <div className="relative">
                <button
                  type="button"
                  aria-expanded={openDropdown === "sources"}
                  onClick={() =>
                    setOpenDropdown((current) => (current === "sources" ? null : "sources"))
                  }
                  className={getFilterTriggerClassName(openDropdown === "sources")}
                >
                  <span>Источников {coverage.unique_sources}</span>
                  <span className="text-xs text-[#8090a3]">{openDropdown === "sources" ? "−" : "+"}</span>
                </button>
                {openDropdown === "sources" ? (
                  <div className="absolute left-0 top-[calc(100%+0.5rem)] z-20 w-[22rem] max-w-[calc(100vw-2rem)] rounded-[1.2rem] border border-[#132642]/10 bg-[#fffdf9] p-4 shadow-[0_18px_50px_rgba(19,38,66,0.14)]">
                    <label className="mb-3 flex items-center gap-2 text-sm font-bold text-[#132642]">
                      <input
                        type="checkbox"
                        checked={selectedSources.length === 0}
                        onChange={() => setSelectedSources([])}
                      />
                      <span>Все источники</span>
                    </label>
                    <div className="flex max-h-72 flex-col gap-2 overflow-y-auto">
                      {availableSourceOptions.map((source) => {
                        const checked = selectedSources.includes(source);
                        return (
                          <label key={source} className="flex items-center gap-2 text-sm font-bold text-[#132642]">
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={(event) => {
                                setSelectedSources((current) => {
                                  if (event.target.checked) {
                                    return [...current, source].sort((left, right) =>
                                      left.localeCompare(right, "ru-RU"),
                                    );
                                  }
                                  return current.filter((item) => item !== source);
                                });
                              }}
                            />
                            <span>{source}</span>
                          </label>
                        );
                      })}
                    </div>
                  </div>
                ) : null}
              </div>

              <div className="relative">
                <button
                  type="button"
                  aria-expanded={openDropdown === "countries"}
                  onClick={() =>
                    setOpenDropdown((current) => (current === "countries" ? null : "countries"))
                  }
                  className={getFilterTriggerClassName(openDropdown === "countries")}
                >
                  <span>Стран {coverage.countries.length}</span>
                  <span className="text-xs text-[#8090a3]">{openDropdown === "countries" ? "−" : "+"}</span>
                </button>
                {openDropdown === "countries" ? (
                  <div className="absolute left-0 top-[calc(100%+0.5rem)] z-20 w-[18rem] max-w-[calc(100vw-2rem)] rounded-[1.2rem] border border-[#132642]/10 bg-[#fffdf9] p-4 shadow-[0_18px_50px_rgba(19,38,66,0.14)]">
                    <label className="mb-3 flex items-center gap-2 text-sm font-bold text-[#132642]">
                      <input
                        type="checkbox"
                        checked={selectedCountries.length === 0}
                        onChange={() => setSelectedCountries([])}
                      />
                      <span>Все страны</span>
                    </label>
                    <div className="flex max-h-72 flex-col gap-2 overflow-y-auto">
                      {availableCountryOptions.map((country) => {
                        const checked = selectedCountries.includes(country.code);
                        return (
                          <label key={country.code} className="flex items-center gap-2 text-sm font-bold text-[#132642]">
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={(event) => {
                                setSelectedCountries((current) => {
                                  if (event.target.checked) {
                                    return [...current, country.code].sort((left, right) =>
                                      left.localeCompare(right, "ru-RU"),
                                    );
                                  }
                                  return current.filter((item) => item !== country.code);
                                });
                              }}
                            />
                            <span>{country.label}</span>
                          </label>
                        );
                      })}
                    </div>
                  </div>
                ) : null}
              </div>

              <div className="relative">
                <button
                  type="button"
                  aria-expanded={openDropdown === "languages"}
                  onClick={() =>
                    setOpenDropdown((current) => (current === "languages" ? null : "languages"))
                  }
                  className={getFilterTriggerClassName(openDropdown === "languages")}
                >
                  <span>Языков {coverage.languages.length}</span>
                  <span className="text-xs text-[#8090a3]">{openDropdown === "languages" ? "−" : "+"}</span>
                </button>
                {openDropdown === "languages" ? (
                  <div className="absolute left-0 top-[calc(100%+0.5rem)] z-20 w-[18rem] max-w-[calc(100vw-2rem)] rounded-[1.2rem] border border-[#132642]/10 bg-[#fffdf9] p-4 shadow-[0_18px_50px_rgba(19,38,66,0.14)]">
                    <label className="mb-3 flex items-center gap-2 text-sm font-bold text-[#132642]">
                      <input
                        type="checkbox"
                        checked={selectedLanguages.length === 0}
                        onChange={() => setSelectedLanguages([])}
                      />
                      <span>Все языки</span>
                    </label>
                    <div className="flex max-h-72 flex-col gap-2 overflow-y-auto">
                      {availableLanguageOptions.map((language) => {
                        const checked = selectedLanguages.includes(language.code);
                        return (
                          <label key={language.code} className="flex items-center gap-2 text-sm font-bold text-[#132642]">
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={(event) => {
                                setSelectedLanguages((current) => {
                                  if (event.target.checked) {
                                    return [...current, language.code].sort((left, right) =>
                                      left.localeCompare(right, "ru-RU"),
                                    );
                                  }
                                  return current.filter((item) => item !== language.code);
                                });
                              }}
                            />
                            <span>{language.label}</span>
                          </label>
                        );
                      })}
                    </div>
                  </div>
                ) : null}
              </div>
            </div>
            <div className="ml-auto flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={handleNarrativesClick}
                disabled={isNarrativesLoading || !result?.items.length}
                className="rounded-full border border-[#dc691f]/35 bg-[#fff4eb] px-4 py-2 text-sm font-bold text-[#132642] transition hover:bg-[#ffe8d6] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isNarrativesLoading ? "AI анализ..." : "AI нарративы"}
              </button>
              <button
                type="button"
                onClick={() => setIsTimelineModalOpen(true)}
                disabled={!narrativeTimelineSeries.length}
                className="rounded-full border border-[#132642]/12 bg-white px-4 py-2 text-sm font-bold text-[#132642] transition hover:border-[#1d4d7c]/35 hover:bg-[#f7fbff] disabled:cursor-not-allowed disabled:opacity-50"
                title={
                  narrativeTimelineSeries.length
                    ? "Открыть таймлайн по уже найденным AI нарративам"
                    : "Сначала выполните AI нарративы"
                }
              >
                Динамика нарративов во времени
              </button>
              <select
                value={sortBy}
                onChange={(event) => setSortBy(event.target.value as DisplaySortMode)}
                className="rounded-full border border-[#132642]/10 bg-white px-4 py-2 text-sm font-bold text-[#132642] outline-none transition focus:border-[#dc691f]/40 focus:ring-4 focus:ring-[#dc691f]/10"
              >
                {DISPLAY_SORT_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <select
                value={cardsPerRow}
                onChange={(event) => setCardsPerRow(Number(event.target.value) as CardsPerRow)}
                className="rounded-full border border-[#132642]/10 bg-white px-4 py-2 text-sm font-bold text-[#132642] outline-none transition focus:border-[#dc691f]/40 focus:ring-4 focus:ring-[#dc691f]/10"
              >
                {CARDS_PER_ROW_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          </section>
        ) : null}

        {result && !visibleItems.length && !error ? (
          <section className="rounded-[1.8rem] border border-[#132642]/12 bg-[#fffdf9]/88 px-5 py-5 text-[15px] leading-7 text-[#5d6d83] shadow-[0_16px_48px_rgba(19,38,66,0.07)] backdrop-blur sm:px-6">
            {selectedCountries.length || selectedSources.length || selectedLanguages.length
              ? "По выбранным фильтрам ничего не найдено. Сними часть ограничений."
              : "Event Registry не нашел статей по этому запросу. Попробуй короче формулировку или переключись на более длинный период."}
          </section>
        ) : null}

        {visibleItems.length ? (
          <section className={`grid gap-5 ${GRID_COLUMNS_CLASSNAME[cardsPerRow]}`}>
            {visibleItems.map((article) => (
              <ArticleCard
                key={`${article.url}-${result?.executed_at ?? "0"}`}
                article={article}
                cardsPerRow={cardsPerRow}
              />
            ))}
          </section>
        ) : null}
      </div>

      {isNarrativesModalOpen ? (
        <div
          className="fixed inset-0 z-40 flex items-center justify-center bg-[#132642]/45 p-4"
          onClick={() => setIsNarrativesModalOpen(false)}
        >
          <div
            className="max-h-[88vh] w-full max-w-4xl overflow-hidden rounded-[1.4rem] border border-[#132642]/12 bg-[#fffdf9] shadow-[0_30px_70px_rgba(19,38,66,0.25)]"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-[#132642]/10 px-6 py-4">
              <div>
                <h2 className="text-lg font-bold text-[#132642]">AI нарративы</h2>
                <p className="text-sm text-[#5d6d83]">
                  {narrativesResult
                    ? `Проанализировано статей: ${narrativesResult.analyzed_articles}`
                    : "Собираем общие нарративы по найденным публикациям"}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setIsNarrativesModalOpen(false)}
                className="rounded-full border border-[#132642]/12 px-3 py-1.5 text-sm font-bold text-[#132642] hover:bg-white"
              >
                Закрыть
              </button>
            </div>
            <div className="max-h-[calc(88vh-5rem)] space-y-3 overflow-y-auto px-6 py-5">
              {isNarrativesLoading ? (
                <p className="rounded-xl border border-[#132642]/10 bg-white px-4 py-3 text-sm text-[#5d6d83]">
                  AI извлекает ключевые нарративы и подтверждающие/оспаривающие цитаты...
                </p>
              ) : null}
              {narrativesError ? (
                <p className="rounded-xl border border-[#a61d24]/20 bg-[#fff6f6] px-4 py-3 text-sm text-[#8d1d24]">
                  {narrativesError}
                </p>
              ) : null}
              {!isNarrativesLoading && !narrativesError && narrativesResult?.narratives.length === 0 ? (
                <p className="rounded-xl border border-[#132642]/10 bg-white px-4 py-3 text-sm text-[#5d6d83]">
                  Нарративы пока не выявлены.
                </p>
              ) : null}
              {narrativesResult?.narratives.map((narrative) => {
                const isOpen = expandedNarratives.includes(narrative.narrative);
                return (
                  <section key={narrative.narrative} className="rounded-2xl border border-[#132642]/10 bg-white p-4">
                    <button
                      type="button"
                      onClick={() =>
                        setExpandedNarratives((current) =>
                          current.includes(narrative.narrative)
                            ? current.filter((item) => item !== narrative.narrative)
                            : [...current, narrative.narrative],
                        )
                      }
                      className="flex w-full items-center justify-between gap-3 text-left"
                    >
                      <div>
                        <p className="text-[15px] font-bold text-[#132642]">{narrative.narrative}</p>
                        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
                          <span className={`rounded-full border px-2.5 py-1 ${getNarrativeStanceClassName(narrative.stance)}`}>
                            {formatNarrativeStance(narrative.stance)}
                          </span>
                          <span className="rounded-full border border-[#132642]/10 px-2.5 py-1 text-[#5d6d83]">
                            В статьях: {narrative.article_count}
                          </span>
                        </div>
                      </div>
                      <span
                        className={`inline-flex h-7 w-7 items-center justify-center rounded-full border border-[#132642]/10 text-lg text-[#8090a3] transition-transform duration-300 ${
                          isOpen ? "rotate-45" : "rotate-0"
                        }`}
                      >
                        +
                      </span>
                    </button>

                    <div
                      className={`grid transition-all duration-300 ease-out ${
                        isOpen
                          ? "mt-3 grid-rows-[1fr] border-t border-[#132642]/8 pt-3 opacity-100"
                          : "grid-rows-[0fr] opacity-0"
                      }`}
                    >
                      <div className="overflow-hidden">
                        <div className="space-y-2">
                        {narrative.evidences.map((evidence) => (
                          (() => {
                            const articleMeta = articleMetaByUrl.get(evidence.article_url);
                            const displayLanguage = evidence.language ?? articleMeta?.language ?? null;
                            const displayDate = articleMeta?.publishedAt ?? null;
                            return (
                              <a
                                key={`${narrative.narrative}-${evidence.article_url}-${evidence.quote.slice(0, 24)}`}
                                href={evidence.article_url}
                                target="_blank"
                                rel="noreferrer"
                                className="block rounded-xl border border-[#132642]/10 bg-[#fffdf9] px-3 py-2 transition hover:border-[#dc691f]/35 hover:bg-[#fff8f1]"
                              >
                                <p className="text-sm font-bold text-[#132642]">{evidence.article_title}</p>
                                <p className="mt-1 text-xs text-[#8090a3]">
                                  {[
                                    evidence.source_name,
                                    formatLanguage(displayLanguage),
                                    displayDate ? formatPublishedAt(displayDate) : null,
                                  ]
                                    .filter(Boolean)
                                    .join(" · ")}
                                </p>
                                <p className="mt-1 text-sm text-[#374a63]">&quot;{evidence.quote}&quot;</p>
                                {evidence.quote_ru ? (
                                  <p className="mt-1 text-sm text-[#5d6d83]">({evidence.quote_ru})</p>
                                ) : null}
                              </a>
                            );
                          })()
                        ))}
                        </div>
                      </div>
                    </div>
                  </section>
                );
              })}
            </div>
          </div>
        </div>
      ) : null}

      {isTimelineModalOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-[#132642]/45 p-4"
          onClick={() => setIsTimelineModalOpen(false)}
        >
          <div
            className="max-h-[88vh] w-full max-w-5xl overflow-hidden rounded-[1.4rem] border border-[#132642]/12 bg-[#fffdf9] shadow-[0_30px_70px_rgba(19,38,66,0.25)]"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-[#132642]/10 px-6 py-4">
              <div>
                <h2 className="text-lg font-bold text-[#132642]">Динамика нарративов во времени</h2>
                <p className="text-sm text-[#5d6d83]">
                  Интерактивный таймлайн покрытия по дням
                </p>
              </div>
              <button
                type="button"
                onClick={() => setIsTimelineModalOpen(false)}
                className="rounded-full border border-[#132642]/12 px-3 py-1.5 text-sm font-bold text-[#132642] hover:bg-white"
              >
                Закрыть
              </button>
            </div>

            <div className="max-h-[calc(88vh-5rem)] space-y-4 overflow-y-auto px-6 py-5">
              {!narrativeTimelineSeries.length ? (
                <p className="rounded-xl border border-[#132642]/10 bg-white px-4 py-3 text-sm text-[#5d6d83]">
                  Сначала выполните анализ по кнопке &quot;AI нарративы&quot;, чтобы построить таймлайн.
                </p>
              ) : (
                <>
                  <div className="flex flex-wrap gap-2">
                    {narrativeTimelineSeries.map((series) => {
                      const isSelected = selectedTimelineNarratives.includes(series.narrative);
                      const narrativeColor = timelineColorMap.get(series.narrative) ?? "#132642";
                      return (
                        <button
                          key={series.narrative}
                          type="button"
                          onClick={() =>
                            setSelectedTimelineNarratives((current) =>
                              current.includes(series.narrative)
                                ? current.filter((item) => item !== series.narrative)
                                : [...current, series.narrative],
                            )
                          }
                          className={`rounded-full border px-3 py-1.5 text-xs font-bold transition ${
                            isSelected
                              ? "border-[#1d4d7c]/35 bg-[#edf5ff] text-[#132642]"
                              : "border-[#132642]/12 bg-white text-[#5d6d83] hover:border-[#1d4d7c]/25"
                          }`}
                        >
                          <span
                            className="mr-2 inline-block h-2.5 w-2.5 rounded-full align-middle"
                            style={{ backgroundColor: narrativeColor }}
                          />
                          {series.narrative} ({series.totalCount})
                        </button>
                      );
                    })}
                  </div>

                  {!selectedTimelineSeries.length ? (
                    <p className="rounded-xl border border-[#132642]/10 bg-white px-4 py-3 text-sm text-[#5d6d83]">
                      Выберите хотя бы один нарратив, чтобы отрисовать таймлайн.
                    </p>
                  ) : (
                    <div className="rounded-2xl border border-[#132642]/10 bg-white p-4">
                      <div className="mb-3 flex items-center justify-between text-xs text-[#8090a3]">
                        <span>Публикаций в день</span>
                        <span>Максимум за день: {timelineMaxCount}</span>
                      </div>
                      <div className="overflow-x-auto">
                        <svg
                          width={Math.max(860, timelineDateKeys.length * 88)}
                          height={340}
                          className="min-w-full"
                          role="img"
                          aria-label="Таймлайн динамики нарративов"
                        >
                          <rect x={0} y={0} width="100%" height="100%" fill="#fff" />
                          {[0, 1, 2, 3, 4].map((step) => {
                            const y = 42 + (220 * step) / 4;
                            const tick = Math.round(timelineMaxCount - (timelineMaxCount * step) / 4);
                            return (
                              <g key={step}>
                                <line x1={70} y1={y} x2={Math.max(800, timelineDateKeys.length * 88)} y2={y} stroke="#e5ecf4" />
                                <text x={48} y={y + 4} fontSize="11" fill="#8090a3" textAnchor="end">
                                  {tick}
                                </text>
                              </g>
                            );
                          })}

                          {timelineDateKeys.map((dateKey, index) => {
                            const x = 90 + index * 88;
                            return (
                              <g key={dateKey}>
                                <line x1={x} y1={42} x2={x} y2={262} stroke="#f1f5fa" />
                                <text x={x} y={292} fontSize="11" fill="#8090a3" textAnchor="middle">
                                  {formatTimelineDateLabel(dateKey)}
                                </text>
                              </g>
                            );
                          })}

                          {narrativeTimelineSeries.map((series) => {
                            const color = timelineColorMap.get(series.narrative) ?? "#132642";
                            const isSelected = selectedTimelineNarratives.includes(series.narrative);
                            const points = timelineDateKeys.map((dateKey, dateIndex) => {
                              const x = 90 + dateIndex * 88;
                              const pointCount = series.points.find((point) => point.dateKey === dateKey)?.count ?? 0;
                              const y = 262 - (pointCount / timelineMaxCount) * 220;
                              return { x, y, count: pointCount, dateKey };
                            });
                            return (
                              <g key={series.narrative}>
                                {points.slice(1).map((point, index) => {
                                  const prev = points[index];
                                  return (
                                    <motion.line
                                      key={`${series.narrative}-segment-${point.dateKey}`}
                                      x1={prev.x}
                                      x2={point.x}
                                      y1={isSelected ? prev.y : 262}
                                      y2={isSelected ? point.y : 262}
                                      stroke={color}
                                      strokeWidth={3}
                                      strokeLinecap="round"
                                      initial={false}
                                      animate={{
                                        y1: isSelected ? prev.y : 262,
                                        y2: isSelected ? point.y : 262,
                                        opacity: isSelected ? 1 : 0.35,
                                      }}
                                      transition={{
                                        duration: 0.55,
                                        ease: [0.22, 1, 0.36, 1],
                                        delay: isSelected ? index * 0.02 : 0,
                                      }}
                                    />
                                  );
                                })}
                                {points.map((point, index) => (
                                  <motion.circle
                                    key={`${series.narrative}-${point.dateKey}`}
                                    cx={point.x}
                                    r={point.count > 0 ? 5 : 3}
                                    fill={point.count > 0 ? color : "#d6e0eb"}
                                    stroke="#fff"
                                    strokeWidth={2}
                                    initial={false}
                                    animate={{
                                      cy: isSelected ? point.y : 262,
                                      opacity: isSelected ? 1 : 0,
                                      scale: isSelected ? 1 : 0.6,
                                    }}
                                    transition={{
                                      duration: 0.5,
                                      ease: [0.22, 1, 0.36, 1],
                                      delay: isSelected ? index * 0.02 : 0,
                                    }}
                                  >
                                    <title>
                                      {series.narrative}: {point.count} ({formatTimelineDateLabel(point.dateKey)})
                                    </title>
                                  </motion.circle>
                                ))}
                              </g>
                            );
                          })}
                        </svg>
                      </div>
                      <div className="mt-3 flex flex-wrap gap-3 text-xs">
                        {selectedTimelineSeries.map((series) => (
                          <span key={`legend-${series.narrative}`} className="inline-flex items-center gap-2 text-[#5d6d83]">
                            <span
                              className="h-2.5 w-2.5 rounded-full"
                              style={{ backgroundColor: timelineColorMap.get(series.narrative) ?? "#132642" }}
                            />
                            <span>{series.narrative}</span>
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      ) : null}

      {isSnapshotsModalOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-[#132642]/45 p-4"
          onClick={() => setIsSnapshotsModalOpen(false)}
        >
          <div
            className="max-h-[88vh] w-full max-w-3xl overflow-hidden rounded-[1.4rem] border border-[#132642]/12 bg-[#fffdf9] shadow-[0_30px_70px_rgba(19,38,66,0.25)]"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-[#132642]/10 px-6 py-4">
              <div>
                <h2 className="text-lg font-bold text-[#132642]">Снимки</h2>
                <p className="text-sm text-[#5d6d83]">История поисков и AI-аналитики нарративов</p>
              </div>
              <button
                type="button"
                onClick={() => setIsSnapshotsModalOpen(false)}
                className="rounded-full border border-[#132642]/12 px-3 py-1.5 text-sm font-bold text-[#132642] hover:bg-white"
              >
                Закрыть
              </button>
            </div>
            <div className="max-h-[calc(88vh-5rem)] space-y-3 overflow-y-auto px-6 py-5">
              {!snapshots.length ? (
                <p className="rounded-xl border border-[#132642]/10 bg-white px-4 py-3 text-sm text-[#5d6d83]">
                  Пока нет сохраненных снимков.
                </p>
              ) : (
                snapshots.map((snapshot) => (
                  <section
                    key={snapshot.id}
                    role="button"
                    tabIndex={0}
                    onClick={() => openSnapshot(snapshot)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        openSnapshot(snapshot);
                      }
                    }}
                    className={`rounded-2xl border bg-white p-4 ${
                      snapshot.id === activeSnapshotId
                        ? "border-[#1d4d7c]/30 shadow-[0_10px_24px_rgba(29,77,124,0.12)]"
                        : "border-[#132642]/10"
                    } cursor-pointer transition hover:border-[#1d4d7c]/30 hover:bg-[#f9fcff]`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-bold text-[#132642]">{snapshot.query}</p>
                        <p className="mt-1 text-xs text-[#8090a3]">
                          {formatPublishedAt(snapshot.savedAt)} · Период {snapshot.lookbackDays}д · Лимит {snapshot.limit}
                        </p>
                        <p className="mt-1 text-xs text-[#5d6d83]">
                          Статей: {snapshot.result.coverage.total_results}
                          {snapshot.narrativesResult
                            ? ` · Нарративов: ${snapshot.narrativesResult.narratives.length}`
                            : " · AI нарративы не запускались"}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            deleteSnapshot(snapshot.id);
                          }}
                          className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-[#a61d24]/20 text-[#8d1d24] hover:bg-[#fff6f6]"
                          aria-label="Удалить снимок"
                          title="Удалить снимок"
                        >
                          <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8">
                            <path d="M4 7h16" />
                            <path d="M9 7V5.8c0-.7.5-1.3 1.2-1.3h3.6c.7 0 1.2.6 1.2 1.3V7" />
                            <path d="M7.2 7l.7 11.1c.1.8.7 1.4 1.5 1.4h5.2c.8 0 1.5-.6 1.5-1.4L16.8 7" />
                            <path d="M10 10.2v6.2" />
                            <path d="M14 10.2v6.2" />
                          </svg>
                        </button>
                      </div>
                    </div>
                  </section>
                ))
              )}
            </div>
          </div>
        </div>
      ) : null}
    </main>
  );
}
