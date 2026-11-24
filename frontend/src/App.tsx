import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import CampaignEditorPage from "./pages/CampaignEditorPage";
import CampaignsPage from "./pages/CampaignsPage";
import CreateCampaignPage from "./pages/CreateCampaignPage";

export default function App() {
  return (
    <div className="layout">
      <header className="topbar">
        <div className="topbar-inner">
          <span className="brand">
            <span className="brand-mark">K</span> Keitaro wrapper
          </span>
          <nav>
            <NavLink to="/new">Новая кампания</NavLink>
            <NavLink to="/campaigns">Кампании</NavLink>
            <a href="/docs" target="_blank" rel="noreferrer">
              API docs
            </a>
          </nav>
        </div>
      </header>
      <main className="content">
        <Routes>
          <Route path="/" element={<Navigate to="/new" replace />} />
          <Route path="/new" element={<CreateCampaignPage />} />
          <Route path="/campaigns" element={<CampaignsPage />} />
          <Route path="/campaigns/:id" element={<CampaignEditorPage />} />
          <Route path="*" element={<p className="muted">Страница не найдена</p>} />
        </Routes>
      </main>
    </div>
  );
}
