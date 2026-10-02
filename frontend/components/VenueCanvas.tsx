"use client";

import {
  Background, BackgroundVariant, BaseEdge, Controls, EdgeLabelRenderer, Handle,
  Position, ReactFlow, getStraightPath, useInternalNode,
  type EdgeProps, type InternalNode, type NodeProps, type OnConnect, type OnEdgesChange, type OnNodesChange,
} from "@xyflow/react";
import { useMemo } from "react";

import { loadColor } from "@/lib/format";
import type { PlaceNode, RouteEdge } from "@/lib/venue";

export interface PlanLoads {
  /** canvas edge id -> load and utilisation */
  routes: Map<string, { load: number; util: number }>;
  /** exit name -> load and utilisation */
  exits: Map<string, { load: number; util: number }>;
}

/**
 * Each node has a visible "drag to connect" dot on its right edge (source) and an
 * invisible centre target. Routes are drawn centre to centre by RouteEdgeView, so
 * handle positions only matter for starting and finishing a connection.
 */
function Handles({ editable }: { editable: boolean }) {
  return (
    <>
      <Handle id="out" type="source" position={Position.Right} isConnectable={editable}
        title="Drag to another area or exit to add a route"
        style={{ width: 11, height: 11, right: -6, border: "2px solid #fff", background: "#4B3FD1",
          opacity: editable ? 1 : 0, pointerEvents: editable ? "all" : "none" }} />
      <Handle id="in" type="target" position={Position.Top} isConnectableStart={false}
        style={{ top: "50%", left: "50%", transform: "translate(-50%, -50%)", width: 1, height: 1,
          opacity: 0, border: 0, pointerEvents: "none" }} />
    </>
  );
}

function PlaceNodeView({ data, selected }: NodeProps<PlaceNode>) {
  const editable = (data as { editable?: boolean }).editable ?? false;
  const type = data.locationType === "zone" ? null : data.locationType;
  return (
    <div className={`relative min-w-[118px] rounded-[3px] border bg-white px-3 py-2 text-ink shadow-[0_1px_0_#15233F14]
      ${selected ? "border-ink outline-2 outline-offset-2 outline-quantum" : "border-ink/70"}`}>
      <div className="font-display text-[15px] font-bold leading-tight">{data.name || "Unnamed"}</div>
      <div className="mt-0.5 flex items-center gap-2 text-[11px] text-ink-soft">
        {type && <span className="capitalize">{type}</span>}
        {data.people > 0 && <span className="num font-semibold text-ink">{data.people} people</span>}
      </div>
      <Handles editable={editable} />
    </div>
  );
}

function ExitNodeView({ data, selected }: NodeProps<PlaceNode>) {
  const editable = (data as { editable?: boolean }).editable ?? false;
  const over = data.util != null && data.util > 1;
  const ring = data.util != null ? loadColor(data.util) : "transparent";
  return (
    <div className={`relative rounded-[2px] bg-exit px-3 py-1.5 text-white ${selected ? "outline-2 outline-offset-2 outline-quantum" : ""}`}
      style={{ boxShadow: data.util != null ? `0 0 0 4px ${ring}` : undefined }}>
      <div className="font-display text-[15px] font-bold leading-tight tracking-wide">{data.name || "Exit"}</div>
      <div className="num text-[11px] text-white/90">
        {data.load != null && data.capacity
          ? <span className={over ? "font-bold" : ""}>{data.load} of {data.capacity}</span>
          : data.capacity ? <>capacity {data.capacity}</> : <>no capacity limit</>}
      </div>
      <Handles editable={editable} />
    </div>
  );
}

function centre(n: InternalNode) {
  return {
    x: n.internals.positionAbsolute.x + (n.measured.width ?? 0) / 2,
    y: n.internals.positionAbsolute.y + (n.measured.height ?? 0) / 2,
  };
}

function RouteEdgeView({ id, source, target, data, selected }: EdgeProps<RouteEdge>) {
  const s = useInternalNode(source), t = useInternalNode(target);
  if (!s || !t) return null;
  const a = centre(s), b = centre(t);
  const [path, labelX, labelY] = getStraightPath({ sourceX: a.x, sourceY: a.y, targetX: b.x, targetY: b.y });
  const hasPlan = data?.util != null;
  const color = hasPlan ? loadColor(data!.util) : "#8E9AAB";
  const width = hasPlan ? 2.5 + 6 * Math.min(data!.util!, 1.5) : 2.5;
  return (
    <>
      {selected && <BaseEdge id={`${id}-sel`} path={path} style={{ stroke: "#4B3FD1", strokeWidth: width + 6, opacity: 0.25 }} />}
      <BaseEdge id={id} path={path} style={{ stroke: color, strokeWidth: width, strokeLinecap: "round" }} />
      <EdgeLabelRenderer>
        <div className="nodrag nopan num pointer-events-auto absolute rounded-[2px] border border-line bg-white/95 px-1.5 py-px text-[10.5px] text-ink"
          style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}>
          {hasPlan
            ? <><b style={{ color: data!.util! > 1 ? "#7A1F3D" : undefined }}>{data!.load}</b> / {data!.capacity}</>
            : <>{data?.capacity} cap, {data?.length} m</>}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}

const nodeTypes = { place: PlaceNodeView, exit: ExitNodeView };
const edgeTypes = { route: RouteEdgeView };

interface Props {
  nodes: PlaceNode[];
  edges: RouteEdge[];
  editable?: boolean;
  loads?: PlanLoads | null;
  onNodesChange?: OnNodesChange<PlaceNode>;
  onEdgesChange?: OnEdgesChange<RouteEdge>;
  onConnect?: OnConnect;
  className?: string;
}

export default function VenueCanvas({
  nodes, edges, editable = false, loads, onNodesChange, onEdgesChange, onConnect, className,
}: Props) {
  // Overlay the plan's loads without touching the editable state.
  const shownNodes = useMemo(() => nodes.map((n) => {
    const l = n.data.locationType === "exit" ? loads?.exits.get(n.data.name) : undefined;
    return { ...n, data: { ...n.data, editable, load: l?.load, util: l?.util } };
  }), [nodes, loads, editable]);
  const shownEdges = useMemo(() => edges.map((e) => {
    const l = loads?.routes.get(e.id);
    return { ...e, data: { ...e.data!, load: l ? l.load : loads ? 0 : undefined, util: l ? l.util : loads ? 0 : undefined } };
  }), [edges, loads]);

  return (
    <div className={className}>
      <ReactFlow
        nodes={shownNodes}
        edges={shownEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        connectionRadius={70}
        nodesDraggable={editable}
        nodesConnectable={editable}
        elementsSelectable={editable}
        deleteKeyCode={editable ? ["Backspace", "Delete"] : null}
        connectionLineStyle={{ stroke: "#4B3FD1", strokeWidth: 2 }}
        fitView
        fitViewOptions={{ padding: 0.18 }}
        minZoom={0.3}
        maxZoom={2}
        proOptions={{ hideAttribution: false }}
      >
        <Background variant={BackgroundVariant.Lines} gap={28} color="#E4E9EF" />
        <Controls showInteractive={false} position="bottom-right" />
      </ReactFlow>
    </div>
  );
}
