"use client";

import { useState, useMemo } from "react";
import { useSave } from "@/components/SaveProvider";
import { PageHead, Section } from "@/components/Shell";
import type { NewsItem } from "@/lib/types";

type NewsCategory = "all" | "race" | "media" | "academy" | "rumor" | "contract" | "rivalry";

const CATEGORY_LABELS: Record<string, string> = {
  race: "Race",
  media: "Media",
  academy: "Academy",
  rumor: "Rumor",
  contract: "Contract",
  incident: "Incident",
  system: "System",
  rivalry: "Rivalry",
};

const FILTER_TABS: Array<{ id: NewsCategory; label: string }> = [
  { id: "all", label: "All" },
  { id: "race", label: "Race" },
  { id: "rumor", label: "Rumors" },
  { id: "contract", label: "Contracts" },
  { id: "academy", label: "Academy" },
  { id: "rivalry", label: "Rivalry" },
];

export function NewsClient() {
  const { currentSave: save, loading, error } = useSave();
  const [filter, setFilter] = useState<NewsCategory>("all");

  const allNews = useMemo(() => (save ? dedupeNewsById(save.news) : []), [save]);
  const filteredNews = useMemo(() => {
    if (!save) return [];
    const news = [...allNews].reverse();
    if (filter === "all") return news;
    return news.filter((item) => item.category === filter);
  }, [save, allNews, filter]);

  const leadStory = filteredNews[0];
  const remainingNews = leadStory ? filteredNews.slice(1) : [];

  if (loading) {
    return (
      <div className="page">
        <p className="loading">Loading news...</p>
      </div>
    );
  }

  if (!save) {
    return (
      <div className="page">
        <div className="empty-state">
          <h2>No Career Save</h2>
          <p>Create a career save to see the news feed.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <PageHead
        meta="Paddock"
        title="News Feed"
        sub={`${allNews.length} stories · Season ${save.season}`}
      />

      {/* Filter tabs */}
      <div className="page-tabs">
        {FILTER_TABS.map((tab) => (
          <div
            key={tab.id}
            className={`page-tab ${filter === tab.id ? "active" : ""}`}
            onClick={() => setFilter(tab.id)}
          >
            {tab.label}
            {tab.id !== "all" && (
              <span className="count">
                {allNews.filter((n) => n.category === tab.id).length}
              </span>
            )}
          </div>
        ))}
      </div>

      {error && <p className="tag neg">{error}</p>}

      {leadStory && (
        <Section>
          <LeadStory news={leadStory} />
        </Section>
      )}

      <Section title={leadStory ? "Latest updates" : undefined}>
        {filteredNews.length === 0 ? (
          <p className="t2">
            No {filter === "all" ? "" : filter} news yet. Complete race weekends to generate news.
          </p>
        ) : (
          <div>
            {remainingNews.length > 0 ? (
              remainingNews.map((item) => <NewsRow key={item.id} news={item} />)
            ) : (
              <p className="t2">No older updates in this category.</p>
            )}
          </div>
        )}
      </Section>
    </div>
  );
}

function dedupeNewsById(news: NewsItem[]) {
  const seen = new Set<string>();
  const dedupedReversed: NewsItem[] = [];
  for (let index = news.length - 1; index >= 0; index -= 1) {
    const item = news[index];
    if (seen.has(item.id)) continue;
    seen.add(item.id);
    dedupedReversed.push(item);
  }
  return dedupedReversed.reverse();
}

function LeadStory({ news }: { news: NewsItem }) {
  return (
    <div className="lead-news">
      <div className="lead-news-main">
        <div className="news-meta">
          <span className="tag solid">Breaking</span>
          <span>{CATEGORY_LABELS[news.category] ?? news.category}</span>
          <span>{news.date}</span>
        </div>
        <h2>{news.headline}</h2>
        <p>{news.body}</p>
      </div>
      <div className="lead-news-score">
        <span className="mono">{news.importance}</span>
        <span>impact</span>
      </div>
    </div>
  );
}

function NewsRow({ news }: { news: NewsItem }) {
  const tagTone =
    news.category === "rivalry"
      ? "warn"
      : news.category === "contract"
      ? "info"
      : news.category === "rumor"
      ? "accent"
      : "";

  return (
    <div className="news-row">
      <div className="news-thumb">{CATEGORY_LABELS[news.category]?.toUpperCase() ?? "NEWS"}</div>
      <div className="news-body">
        <div className="news-meta">
          <span className={`tag ${tagTone}`} style={{ fontSize: 10 }}>
            {CATEGORY_LABELS[news.category] ?? news.category}
          </span>
          <span>{news.date}</span>
          {news.importance >= 4 && <span className="tag accent" style={{ fontSize: 10 }}>Important</span>}
        </div>
        <div className="news-headline">{news.headline}</div>
        <div className="news-summary">{news.body}</div>
      </div>
    </div>
  );
}
