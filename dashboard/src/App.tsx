import { Link, NavLink, Route, Routes } from "react-router";
import { ClaimPage } from "./ClaimPage";
import { InstructionsPage } from "./InstructionsPage";
import { QueuePage } from "./QueuePage";

export function App() {
  return (
    <>
      <header className="header">
        <Link to="/" className="brand">
          UnderCover
        </Link>
        <span className="tagline">Claims desk</span>
        <nav className="nav">
          <NavLink to="/" end>
            Queue
          </NavLink>
          <NavLink to="/instructions">Instructions</NavLink>
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<QueuePage />} />
          <Route path="/claims/:claimId" element={<ClaimPage />} />
          <Route path="/instructions" element={<InstructionsPage />} />
          <Route path="*" element={<p>There is no page here.</p>} />
        </Routes>
      </main>
    </>
  );
}
