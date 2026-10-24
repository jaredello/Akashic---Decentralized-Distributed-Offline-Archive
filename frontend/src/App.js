/**
 * The app's root: sets up page routes (home, article, Burn to Disc, Source) around the shared
 * header and the Disk Monitor sidebar.
 */
import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import { DiskProvider } from "@/context/DiskContext";
import { Header } from "@/components/Header";
import { DiskMonitor } from "@/components/DiskMonitor";
import Portal from "@/pages/Portal";
import Article from "@/pages/Article";
import Burn from "@/pages/Burn";
import Source from "@/pages/Source";

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
            <Route path="/source" element={<Source />} />
          </Routes>
          <DiskMonitor />
        </DiskProvider>
      </BrowserRouter>
      <Toaster position="top-right" richColors />
    </div>
  );
}

export default App;
