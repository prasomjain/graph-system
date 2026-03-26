import React, { useMemo, useState } from "react";
import axios from "axios";
import { MessageSquareText, SendHorizonal } from "lucide-react";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

function nowLabel() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function ChatBox({ onHighlightPath }) {
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [messages, setMessages] = useState(() => [
    {
      role: "assistant",
      text: "Ask an ERP flow question like: Trace Sales Order 740506 through delivery, invoice, and payment.",
      time: nowLabel(),
    },
  ]);

  const canSend = useMemo(() => input.trim().length > 0 && !isLoading, [input, isLoading]);

  const sendMessage = async () => {
    const trimmed = input.trim();
    if (!trimmed || isLoading) {
      return;
    }

    setMessages((prev) => [...prev, { role: "user", text: trimmed, time: nowLabel() }]);
    setInput("");
    setIsLoading(true);

    try {
      const response = await axios.post(`${API_BASE}/api/chat`, { message: trimmed }, { timeout: 30000 });
      const data = response.data || {};

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: data.answer || "No response.",
          time: nowLabel(),
        },
      ]);

      if (Array.isArray(data.relevant_node_ids)) {
        onHighlightPath?.(data.relevant_node_ids);
      }
    } catch (error) {
      const apiError = error?.response?.data?.detail;
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: typeof apiError === "string" ? apiError : "Request failed. Check backend status and try again.",
          time: nowLabel(),
        },
      ]);
      onHighlightPath?.([]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <section className="flex h-full flex-col rounded-2xl border border-panelBorder bg-panel/90 shadow-panel panel-enter">
      <header className="flex items-center gap-3 border-b border-slate-800 px-4 py-3">
        <div className="rounded-lg bg-cyan-400/10 p-2 text-cyan-300">
          <MessageSquareText size={18} />
        </div>
        <div>
          <h2 className="text-sm font-semibold text-slate-100">ERP Analyst Chat</h2>
          <p className="text-xs text-slate-400">Grounded responses from context graph only</p>
        </div>
      </header>

      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {messages.map((msg, index) => (
          <article
            key={`${msg.role}-${index}`}
            className={`max-w-[95%] rounded-xl px-3 py-2 text-sm leading-relaxed ${
              msg.role === "user"
                ? "ml-auto border border-cyan-500/30 bg-cyan-500/10 text-cyan-100"
                : "border border-slate-700 bg-slate-900/60 text-slate-200"
            }`}
          >
            <p>{msg.text}</p>
            <p className="mt-1 text-[10px] uppercase tracking-wider text-slate-500">{msg.time}</p>
          </article>
        ))}

        {isLoading && (
          <div className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-2 text-xs text-slate-300">
            <span className="h-2 w-2 animate-pulse rounded-full bg-cyan-300" />
            Analyzing graph...
          </div>
        )}
      </div>

      <footer className="border-t border-slate-800 p-3">
        <div className="flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-900/80 px-2 py-2 focus-within:border-cyan-400/50">
          <input
            type="text"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                sendMessage();
              }
            }}
            placeholder="Ask about orders, deliveries, invoices, payments..."
            className="w-full bg-transparent px-2 text-sm text-slate-100 outline-none placeholder:text-slate-500"
          />
          <button
            type="button"
            onClick={sendMessage}
            disabled={!canSend}
            className="rounded-lg bg-cyan-500 px-3 py-2 text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-50"
            aria-label="Send message"
          >
            <SendHorizonal size={16} />
          </button>
        </div>
      </footer>
    </section>
  );
}
