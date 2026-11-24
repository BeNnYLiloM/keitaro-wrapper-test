import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type CampaignDetails, type Meta, type Offer } from "../api";
import GeoInput from "../components/GeoInput";
import OfferAutocomplete from "../components/OfferAutocomplete";
import { useToast } from "../components/Toasts";
import { refLabel } from "../utils";

export default function CreateCampaignPage() {
  const toast = useToast();
  const [meta, setMeta] = useState<Meta | null>(null);
  const [countries, setCountries] = useState<string[]>([]);
  const [name, setName] = useState("");
  const [geo, setGeo] = useState<string[]>([]);
  const [offer, setOffer] = useState<Offer | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [created, setCreated] = useState<CampaignDetails | null>(null);

  useEffect(() => {
    api.countries().then(setCountries).catch((e) => toast.error(`Список стран: ${e.message}`));
    api.meta().then(setMeta).catch((e) => toast.error(`Справочники Keitaro: ${e.message}`));
  }, [toast]);

  const canSubmit = name.trim() && geo.length > 0 && offer && !submitting;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit || !offer) return;
    setSubmitting(true);
    try {
      const campaign = await api.createCampaign({ name: name.trim(), geo, offer_id: offer.id });
      setCreated(campaign);
      toast.success(`Кампания #${campaign.id} создана`);
      setName("");
      setGeo([]);
      setOffer(null);
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="page-grid">
      <section className="card">
        <h1>Новая кампания</h1>
        <form onSubmit={submit} className="form">
          <label className="field">
            <span className="label">Name</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Имя кампании"
              maxLength={255}
              disabled={submitting}
            />
          </label>

          <div className="field">
            <span className="label">Geo</span>
            <GeoInput value={geo} onChange={setGeo} countries={countries} disabled={submitting} />
          </div>

          <div className="field">
            <span className="label">Offer</span>
            <OfferAutocomplete value={offer} onChange={setOffer} disabled={submitting} />
          </div>

          <button className="btn btn-primary btn-wide" disabled={!canSubmit}>
            {submitting ? "Создаём…" : "Create"}
          </button>
        </form>
      </section>

      <aside className="card side">
        <h2>Что будет создано</h2>
        <dl className="kv">
          <dt>Домен</dt>
          <dd>{meta ? refLabel(meta.domain) : "…"}</dd>
          <dt>Группа</dt>
          <dd>{meta ? refLabel(meta.group) : "…"}</dd>
          <dt>Источник</dt>
          <dd>{meta ? refLabel(meta.traffic_source) : "…"}</dd>
        </dl>
        <ol className="flow-preview">
          <li>
            <b>Поток 1</b> — посетители из{" "}
            {geo.length ? <span className="mono">{geo.join(", ")}</span> : <span className="muted">выбранных стран</span>}{" "}
            → редирект на <span className="mono">{meta?.google_url ?? "https://google.com"}</span>
          </li>
          <li>
            <b>Поток 2</b> — все остальные →{" "}
            {offer ? (
              <>
                оффер <span className="mono">#{offer.id}</span> {offer.name} (100%)
              </>
            ) : (
              <span className="muted">выбранный оффер</span>
            )}
          </li>
        </ol>

        {created && (
          <div className="created">
            <h3>
              Создано: #{created.id} «{created.name}»
            </h3>
            <ul className="links">
              <li>
                <Link to={`/campaigns/${created.id}`}>Открыть в редакторе →</Link>
              </li>
              <li>
                <a href={created.keitaro_url} target="_blank" rel="noreferrer">
                  Открыть в Keitaro ↗
                </a>
              </li>
              {created.tracking_url && (
                <li>
                  Ссылка кампании: <span className="mono">{created.tracking_url}</span>
                </li>
              )}
            </ul>
          </div>
        )}
      </aside>
    </div>
  );
}
