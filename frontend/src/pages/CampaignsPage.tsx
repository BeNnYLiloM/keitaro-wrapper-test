import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type Campaign } from "../api";
import { useToast } from "../components/Toasts";

const PAGE = 50;

export default function CampaignsPage() {
  const toast = useToast();
  const navigate = useNavigate();
  const [items, setItems] = useState<Campaign[]>([]);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [onlyMine, setOnlyMine] = useState(false);
  const [deleting, setDeleting] = useState<number | null>(null);
  const [jumpId, setJumpId] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await api.listCampaigns(offset, PAGE));
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [offset, toast]);

  useEffect(() => {
    load();
  }, [load]);

  const remove = async (c: Campaign) => {
    if (!confirm(`Удалить кампанию #${c.id} «${c.name}» вместе с потоками? Архива на стенде нет.`)) return;
    setDeleting(c.id);
    try {
      await api.deleteCampaign(c.id);
      toast.success(`Кампания #${c.id} удалена`);
      setItems((list) => list.filter((x) => x.id !== c.id));
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setDeleting(null);
    }
  };

  const visible = onlyMine ? items.filter((c) => c.created_by_wrapper) : items;

  return (
    <section className="card">
      <div className="card-head">
        <h1>Кампании</h1>
        <div className="toolbar">
          <label className="check">
            <input type="checkbox" checked={onlyMine} onChange={(e) => setOnlyMine(e.target.checked)} />
            Только созданные здесь
          </label>
          <form
            className="jump"
            onSubmit={(e) => {
              e.preventDefault();
              if (/^\d+$/.test(jumpId)) navigate(`/campaigns/${jumpId}`);
            }}
          >
            <input value={jumpId} onChange={(e) => setJumpId(e.target.value)} placeholder="ID кампании" />
            <button className="btn">Открыть</button>
          </form>
          <button className="btn" onClick={load} disabled={loading}>
            Обновить
          </button>
          <Link className="btn btn-primary" to="/new">
            + Новая
          </Link>
        </div>
      </div>

      {loading ? (
        <p className="muted">Загрузка…</p>
      ) : visible.length === 0 ? (
        <p className="muted">
          Кампаний нет. <Link to="/new">Создать первую</Link>
        </p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Название</th>
              <th>Alias</th>
              <th>Гео</th>
              <th>Группа</th>
              <th>Источник</th>
              <th>Статус</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {visible.map((c) => (
              <tr key={c.id}>
                <td className="mono">{c.id}</td>
                <td>
                  <Link to={`/campaigns/${c.id}`}>{c.name}</Link>
                  {c.created_by_wrapper && <span className="badge badge-soft">wrapper</span>}
                </td>
                <td className="mono">{c.alias ?? "—"}</td>
                <td className="mono">{c.geo?.join(", ") ?? "—"}</td>
                <td>{c.group?.name ?? (c.group ? `#${c.group.id}` : "—")}</td>
                <td>{c.traffic_source?.name ?? (c.traffic_source ? `#${c.traffic_source.id}` : "—")}</td>
                <td>
                  <span className={`badge ${c.state === "active" ? "badge-green" : ""}`}>{c.state ?? "—"}</span>
                </td>
                <td className="actions">
                  <Link className="btn btn-sm" to={`/campaigns/${c.id}`}>
                    Редактировать
                  </Link>
                  <a className="btn btn-sm" href={c.keitaro_url} target="_blank" rel="noreferrer">
                    Keitaro ↗
                  </a>
                  <button className="btn btn-sm btn-danger" disabled={deleting === c.id} onClick={() => remove(c)}>
                    Удалить
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="pager">
        <button className="btn" disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
          ← Назад
        </button>
        <span className="muted">
          {offset + 1}–{offset + items.length}
        </span>
        <button className="btn" disabled={items.length < PAGE || loading} onClick={() => setOffset(offset + PAGE)}>
          Вперёд →
        </button>
      </div>
    </section>
  );
}
