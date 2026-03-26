import React, { useRef } from "react";
import GraphView from "./components/GraphView";
import ChatBox from "./components/ChatBox";

export default function App() {
  const graphRef = useRef(null);

  const handleHighlightPath = (nodeIds) => {
    graphRef.current?.highlightPath(nodeIds);
  };

  return (
    <main className="h-screen w-full overflow-hidden px-4 py-4 text-slate-100">
      <div className="mx-auto flex h-full max-w-[1800px] flex-col gap-4">
        <header className="rounded-2xl border border-panelBorder bg-slate-900/70 px-5 py-4 shadow-panel backdrop-blur panel-enter">
          <p className="text-xs uppercase tracking-[0.25em] text-cyan-300">Dodge AI</p>
          <h1 className="mt-1 font-display text-2xl font-semibold">Enterprise ERP Context Graph Dashboard</h1>
        </header>

        <section className="grid h-[calc(100%-96px)] grid-cols-1 gap-4 xl:grid-cols-[7fr_3fr]">
          <div className="min-h-[52vh] xl:min-h-0">
            <GraphView ref={graphRef} />
          </div>
          <div className="min-h-[42vh] xl:min-h-0">
            <ChatBox onHighlightPath={handleHighlightPath} />
          </div>
        </section>
      </div>
    </main>
  );
}
