import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { DiskProvider } from "@/context/DiskContext";
import { Header } from "@/components/Header";
import { DiskMonitor } from "@/components/DiskMonitor";
import Portal from "@/pages/Portal";
import Article from "@/pages/Article";
import Burn from "@/pages/Burn";

function App() {
  return (
    <div className="App min-h-screen bg-white">
      <BrowserRouter>
        <DiskProvider>
          <Header />
          <Routes>
            <Route path="/" element={<Portal />} />
            <Route path="/wiki/:slug" element={<Article />} />
            <Route path="/burn" element={<Burn />} />
          </Routes>
          <DiskMonitor />
        </DiskProvider>
      </BrowserRouter>
    </div>
  );
}

export default App;
