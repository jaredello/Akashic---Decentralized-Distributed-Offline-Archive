import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { DiskProvider } from "@/context/DiskContext";
import { Header } from "@/components/Header";
import { DiskMonitor } from "@/components/DiskMonitor";
import Portal from "@/pages/Portal";
import Article from "@/pages/Article";

function App() {
  return (
    <div className="App min-h-screen bg-white">
      <BrowserRouter>
        <DiskProvider>
          <Header />
          <Routes>
            <Route path="/" element={<Portal />} />
            <Route path="/wiki/:slug" element={<Article />} />
          </Routes>
          <DiskMonitor />
        </DiskProvider>
      </BrowserRouter>
    </div>
  );
}

export default App;
