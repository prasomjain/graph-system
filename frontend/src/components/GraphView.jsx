import React, {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import ForceGraph2D from "react-force-graph-2d";
import graphDataRaw from "../assets/processed_graph.json";

const TYPE_COLORS = {
  sales_order_headers: "#60a5fa",
  sales_order_items: "#3b82f6",
  outbound_delivery_headers: "#fb923c",
  outbound_delivery_items: "#f97316",
  billing_document_headers: "#4ade80",
  billing_document_items: "#22c55e",
  payments_accounts_receivable: "#f472b6",
  journal_entry_items_accounts_receivable: "#a78bfa",
  business_partners: "#fde047",
  products: "#67e8f9",
};

function asId(value) {
  if (value && typeof value === "object") {
    return String(value.id ?? "");
  }
  return String(value ?? "");
}

function edgeKey(source, target) {
  return `${source}->${target}`;
}

const GraphView = forwardRef(function GraphView(_, ref) {
  const containerRef = useRef(null);
  const fgRef = useRef(null);
  const [selectedNode, setSelectedNode] = useState(null);
  const [hoveredNode, setHoveredNode] = useState(null);
  const [highlightedNodeIds, setHighlightedNodeIds] = useState(() => new Set());
  const [highlightedLinkIds, setHighlightedLinkIds] = useState(() => new Set());
  const [graphSize, setGraphSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return undefined;
    }

    let frameId = 0;
    const updateSize = () => {
      const nextWidth = Math.max(320, Math.floor(container.clientWidth));
      const nextHeight = Math.max(320, Math.floor(container.clientHeight));
      setGraphSize((prev) => {
        if (prev.width === nextWidth && prev.height === nextHeight) {
          return prev;
        }
        return { width: nextWidth, height: nextHeight };
      });
    };

    updateSize();

    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frameId);
      frameId = requestAnimationFrame(updateSize);
    });
    observer.observe(container);

    return () => {
      observer.disconnect();
      cancelAnimationFrame(frameId);
    };
  }, []);

  const graphData = useMemo(() => {
    const nodes = Array.isArray(graphDataRaw.nodes) ? graphDataRaw.nodes.map((n) => ({ ...n })) : [];
    const links = Array.isArray(graphDataRaw.links) ? graphDataRaw.links.map((l) => ({ ...l })) : [];
    return { nodes, links };
  }, []);

  const highlightPath = useCallback(
    (nodeIds) => {
      const ids = new Set((nodeIds || []).map((id) => String(id)));
      setHighlightedNodeIds(ids);

      const linkIds = new Set();
      graphData.links.forEach((link) => {
        const source = asId(link.source);
        const target = asId(link.target);
        if (ids.has(source) || ids.has(target)) {
          linkIds.add(edgeKey(source, target));
        }
      });
      setHighlightedLinkIds(linkIds);

      const firstId = [...ids][0];
      if (!firstId || !fgRef.current) {
        return;
      }

      const node = graphData.nodes.find((n) => String(n.id) === firstId);
      if (!node || typeof node.x !== "number" || typeof node.y !== "number") {
        return;
      }

      fgRef.current.centerAt(node.x, node.y, 600);
      fgRef.current.zoom(2.2, 700);
    },
    [graphData]
  );

  useImperativeHandle(ref, () => ({
    highlightPath,
  }));

  const nodeColor = useCallback(
    (node) => {
      const id = String(node.id ?? "");
      if (highlightedNodeIds.has(id)) {
        return "#facc15";
      }

      if (hoveredNode && String(hoveredNode.id) === id) {
        return "#e2e8f0";
      }

      return TYPE_COLORS[node.entity_type] || "#94a3b8";
    },
    [highlightedNodeIds, hoveredNode]
  );

  const nodeSize = useCallback(
    (node) => {
      const id = String(node.id ?? "");
      if (highlightedNodeIds.has(id)) {
        return 6;
      }
      return 3.5;
    },
    [highlightedNodeIds]
  );

  const linkColor = useCallback(
    (link) => {
      const source = asId(link.source);
      const target = asId(link.target);
      return highlightedLinkIds.has(edgeKey(source, target))
        ? "rgba(250, 204, 21, 0.95)"
        : "rgba(148, 163, 184, 0.25)";
    },
    [highlightedLinkIds]
  );

  const linkWidth = useCallback(
    (link) => {
      const source = asId(link.source);
      const target = asId(link.target);
      return highlightedLinkIds.has(edgeKey(source, target)) ? 2.8 : 0.75;
    },
    [highlightedLinkIds]
  );

  return (
    <div
      ref={containerRef}
      className="relative h-full w-full overflow-hidden rounded-2xl border border-panelBorder bg-panel/80 shadow-panel panel-enter"
    >
      <div className="absolute left-4 top-4 z-20 rounded-lg border border-cyan-300/20 bg-slate-900/70 px-3 py-2 text-xs text-slate-200 backdrop-blur">
        <p className="font-semibold text-cyan-300">Context Graph</p>
        <p>Nodes: {graphData.nodes.length}</p>
        <p>Links: {graphData.links.length}</p>
      </div>

      <ForceGraph2D
        ref={fgRef}
        graphData={graphData}
        width={graphSize.width}
        height={graphSize.height}
        nodeLabel={(node) => String(node.id ?? "")}
        nodeColor={nodeColor}
        nodeVal={nodeSize}
        linkColor={linkColor}
        linkWidth={linkWidth}
        backgroundColor="rgba(2, 6, 23, 0)"
        onNodeHover={setHoveredNode}
        onNodeClick={(node) => {
          setSelectedNode(node);
          if (fgRef.current && typeof node.x === "number" && typeof node.y === "number") {
            fgRef.current.centerAt(node.x, node.y, 450);
            fgRef.current.zoom(2.4, 450);
          }
        }}
        cooldownTicks={80}
      />

      {selectedNode && (
        <aside className="absolute bottom-4 right-4 z-30 max-h-[45vh] w-[330px] overflow-auto rounded-xl border border-emerald-300/20 bg-slate-900/85 p-4 text-xs text-slate-200 backdrop-blur">
          <div className="mb-3 flex items-start justify-between gap-3">
            <div>
              <p className="text-[11px] uppercase tracking-widest text-emerald-300">Node Metadata</p>
              <p className="mt-1 break-all text-sm font-semibold text-white">{String(selectedNode.id ?? "")}</p>
            </div>
            <button
              type="button"
              className="rounded-md border border-slate-600 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-800"
              onClick={() => setSelectedNode(null)}
            >
              Close
            </button>
          </div>
          <div className="space-y-1">
            {Object.entries(selectedNode).map(([key, value]) => (
              <div key={key} className="rounded-md bg-slate-800/60 px-2 py-1">
                <p className="text-[10px] uppercase tracking-wide text-slate-400">{key}</p>
                <p className="break-all text-slate-200">
                  {typeof value === "object" ? JSON.stringify(value) : String(value)}
                </p>
              </div>
            ))}
          </div>
        </aside>
      )}
    </div>
  );
});

export default GraphView;
