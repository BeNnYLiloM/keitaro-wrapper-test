import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type CampaignDetails, type Operation, type Stream } from "../api";
import OffersEditor from "../components/OffersEditor";
import { countryName, formatDate, refLabel } from "../utils";

export default function CampaignEditorPage() {
  const { id } = useParams();
  const campaignId = Number(id);
  const [campaign, setCampaign] = useState<CampaignDetails | null>(null);
  const [operations, setOperations] = useState<Operation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [dirtyStreams, setDirtyStreams] = useState<Set<number>>(new Set());
  const hasDraft = dirtyStreams.size > 0;

  const setStreamDirty = useCallback((streamId: number, dirty: boolean) => {
    setDirtyStreams((prev) => {
      if (prev.has(streamId) === dirty) return prev;
      const next = new Set(prev);
      if (dirty) next.add(streamId);
      else next.delete(streamId);
      return next;
    });
  }, []);

  // не даём молча закрыть вкладку с неопубликованным черновиком
  useEffect(() => {
    if (!hasDraft) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [hasDraft]);

  const loadOperations = useCallback(() => {
    api.operations(campaignId).then(setOperations).catch(() => setOperations([]));
  }, [campaignId]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setCampaign(await api.getCampaign(campaignId));
      loadOperations();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [campaignId, loadOperations]);

  useEffect(() => {
    load();
  }, [load]);

  const replaceStream = (stream: Stream) => {
    setCampaign((c) => (c ? { ...c, streams: c.streams.map((s) => (s.id === stream.id ? stream : s)) } : c));
    loadOperations();
  };

  const refresh = () => {
    if (hasDraft && !confirm("Есть неопубликованные изменения офферов. Обновить и потерять их?")) return;
    load();
  };

  if (loading && !campaign) return <p className="muted">Загрузка…</p>;
  if (error)
    return (
      <section className="card">
        <p className="error-text">{error}</p>
        <Link to="/campaigns">← К списку кампаний</Link>
      </section>
    );
  if (!campaign) return null;

  return (
    <div className="stack">
      <section className="card">
        <div className="card-head">
          <div>
            <Link to="/campaigns" className="muted small">
              ← Кампании
            </Link>
            <h1>
              {campaign.name} <span className="muted">#{campaign.id}</span>
            </h1>
          </div>
          <div className="toolbar">
            <span className={`badge ${campaign.state === "active" ? "badge-green" : ""}`}>{campaign.state ?? "—"}</span>
            <button className="btn" onClick={refresh} disabled={loading}>
              Обновить
            </button>
            <a className="btn" href={campaign.keitaro_url} target="_blank" rel="noreferrer">
              Открыть в Keitaro ↗
            </a>
          </div>
        </div>
        <div className="kv-inline">
          <span>
            <span className="muted">Alias</span> <span className="mono">{campaign.alias ?? "—"}</span>
          </span>
          <span>
            <span className="muted">Домен</span> {refLabel(campaign.domain)}
          </span>
          <span>
            <span className="muted">Группа</span> {refLabel(campaign.group)}
          </span>
          <span>
            <span className="muted">Источник</span> {refLabel(campaign.traffic_source)}
          </span>
          {campaign.tracking_url && (
            <span>
              <span className="muted">Ссылка</span> <span className="mono">{campaign.tracking_url}</span>
            </span>
          )}
        </div>
      </section>

      {campaign.streams.length === 0 && <p className="muted">В кампании нет потоков.</p>}
      {campaign.streams.map((stream, index) => (
        <StreamCard
          key={stream.id}
          index={index + 1}
          stream={stream}
          onUpdated={replaceStream}
          onDirtyChange={setStreamDirty}
          onActivity={loadOperations}
          dirty={dirtyStreams.has(stream.id)}
        />
      ))}

      <section className="card">
        <h2>История изменений через обёртку</h2>
        {operations.length === 0 ? (
          <p className="muted">Пока пусто.</p>
        ) : (
          <table className="table compact">
            <thead>
              <tr>
                <th>Время</th>
                <th>Операция</th>
                <th>Поток</th>
                <th>Детали</th>
              </tr>
            </thead>
            <tbody>
              {operations.map((op) => (
                <tr key={op.id} className={op.success ? "" : "row-error"}>
                  <td className="mono">{formatDate(op.created_at)}</td>
                  <td>{operationLabel(op.operation)}</td>
                  <td className="mono">{op.stream_id ?? "—"}</td>
                  <td>{op.success ? operationDetails(op) : <span className="error-text">{op.error}</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

type StreamCardProps = {
  index: number;
  stream: Stream;
  dirty: boolean;
  onUpdated: (s: Stream) => void;
  onDirtyChange: (streamId: number, dirty: boolean) => void;
  onActivity: () => void;
};

function StreamCard({ index, stream, dirty, onUpdated, onDirtyChange, onActivity }: StreamCardProps) {
  const reportDirty = useCallback((d: boolean) => onDirtyChange(stream.id, d), [onDirtyChange, stream.id]);

  return (
    <section className={`card stream ${dirty ? "stream-dirty" : ""}`}>
      <div className="card-head">
        <h2>
          <span className={`dot ${stream.state === "active" ? "dot-green" : ""}`} />
          Поток {index}: {stream.name ?? `#${stream.id}`} <span className="muted small">#{stream.id}</span>
          {dirty && <span className="badge badge-draft">черновик</span>}
        </h2>
        <div className="toolbar small muted">
          {stream.type} · {schemaLabel(stream.stream_schema)}
        </div>
      </div>

      {stream.filters.length > 0 && (
        <div className="filters">
          <span className="label">Фильтры</span>
          {stream.filters.map((f, i) => (
            <span key={i} className="filter">
              {filterLabel(f.name)}: {f.mode === "reject" ? "отклонять" : "принимать"}{" "}
              <b>{Array.isArray(f.payload) ? f.payload.join(", ") : String(f.payload ?? "")}</b>
              {f.name === "country" && Array.isArray(f.payload) && (
                <span className="muted"> ({(f.payload as string[]).map(countryName).join(", ")})</span>
              )}
            </span>
          ))}
        </div>
      )}

      {stream.stream_schema === "redirect" && (
        <p>
          Редирект ({stream.action_type}) → <span className="mono">{String(stream.action_payload ?? "")}</span>
        </p>
      )}

      {stream.editable && (
        <OffersEditor stream={stream} onPublished={onUpdated} onDirtyChange={reportDirty} onActivity={onActivity} />
      )}
    </section>
  );
}

function schemaLabel(schema: string | null): string {
  switch (schema) {
    case "landings":
      return "лендинги и офферы";
    case "redirect":
      return "редирект";
    case "action":
      return "действие";
    default:
      return schema ?? "—";
  }
}

function filterLabel(name: string): string {
  return name === "country" ? "Страна" : name;
}

function operationLabel(op: string): string {
  return (
    {
      create_campaign: "Создание кампании",
      add_offer: "Добавлен оффер",
      remove_offer: "Удалён оффер",
      publish_offers: "Публикация офферов",
      pin_offer: "Доля закреплена",
      unpin_offer: "Доля откреплена",
      delete_campaign: "Удаление кампании",
    }[op] ?? op
  );
}

function operationDetails(op: Operation): string {
  const p = op.payload ?? {};
  const after = (p.after as { offer_id: number; share: number }[] | undefined) ?? [];
  if (op.operation === "publish_offers") {
    const pinned = new Set((p.pinned as number[] | undefined) ?? []);
    const added = (p.added as number[] | undefined) ?? [];
    const restored = (p.restored as number[] | undefined) ?? [];
    const removed = (p.removed as number[] | undefined) ?? [];
    const parts = [
      added.length ? `+${added.map((id) => `#${id}`).join(", ")}` : "",
      restored.length ? `↺${restored.map((id) => `#${id}`).join(", ")}` : "",
      removed.length ? `−${removed.map((id) => `#${id}`).join(", ")}` : "",
    ].filter(Boolean);
    const shares = after.map((o) => `${o.offer_id}: ${o.share}%${pinned.has(o.offer_id) ? " 📌" : ""}`).join(", ");
    return `${parts.length ? parts.join(" ") + " → " : ""}${shares}`;
  }
  if (op.operation === "pin_offer" || op.operation === "unpin_offer") {
    return `#${p.offer_id}: ${p.share}%`;
  }
  if (op.operation === "add_offer" || op.operation === "remove_offer") {
    return `#${p.offer_id} → ${after.map((o) => `${o.offer_id}: ${o.share}%`).join(", ")}`;
  }
  if (op.operation === "create_campaign") {
    return `гео ${(p.geo as string[] | undefined)?.join(", ") ?? "—"}, оффер #${p.offer_id}`;
  }
  return "";
}
