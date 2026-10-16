"use client";
// WHAT THIS FILE IS FOR: the interactive venue map, drawn as boxes (areas and exits) joined by lines (routes).
// In the Lab it is editable: drag boxes and draw new routes. Elsewhere it is view only.
// When a plan is shown, routes and exits are coloured and thickened by how busy they are.
// It is built on React Flow, a ready made library for drawing boxes and connecting lines.

import {
  Background, BackgroundVariant, BaseEdge, Controls, EdgeLabelRenderer, Handle,
  Position, ReactFlow, getStraightPath, useInternalNode,
  type EdgeProps, type InternalNode, type NodeProps, type OnConnect, type OnEdgesChange, type OnNodesChange,
} from "@xyflow/react";
import { useMemo } from "react";

import { loadColor } from "@/lib/format";
import type { PlaceNode, RouteEdge } from "@/lib/venue";

// How many people a plan sends along each route and through each exit, and how full that makes them.
export interface PlanLoads {
  /** canvas edge id -> load and utilisation */
  routes: Map<string, { load: number; util: number }>;
  /** exit name -> load and utilisation */
  exits: Map<string, { load: number; util: number }>;
}

// Adds the two connection points to a box: a purple dot to drag from, and a hidden landing spot.
// The dot is only shown when the map can be edited.
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

// Draws an ordinary area box: its name, its type, how many people are there and how many groups.
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
        {data.people > 0 && data.groups > 1 && <span className="num rounded-[2px] bg-quantum-soft px-1 font-semibold text-quantum">{data.groups} groups</span>}
      </div>
      <Handles editable={editable} />
    </div>
  );
}

// Draws a green exit sign box. With a plan shown, a coloured ring shows how full the exit is,
// and the text reads "load of capacity", in bold when it is over capacity.
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

// Finds the middle point of a box on the map, so routes can run centre to centre.
function centre(n: InternalNode) {
  return {
    x: n.internals.positionAbsolute.x + (n.measured.width ?? 0) / 2,
    y: n.internals.positionAbsolute.y + (n.measured.height ?? 0) / 2,
  };
}

// Draws one route as a straight line with a small label in the middle.
// With a plan, the line gets busier colours and grows thicker as it fills; the label shows people sent out of its capacity.
// Without a plan, the label shows the route's capacity, length and any fixed travel time.
function RouteEdgeView({ id, source, target, data, selected }: EdgeProps<RouteEdge>) {
  // Step 1: find the centres of the two boxes and the straight line between them.
  const s = useInternalNode(source), t = useInternalNode(target);
  if (!s || !t) return null;
  const a = centre(s), b = centre(t);
  const [path, labelX, labelY] = getStraightPath({ sourceX: a.x, sourceY: a.y, targetX: b.x, targetY: b.y });
  // Step 2: pick the colour and thickness: grey and thin with no plan, coloured by fullness with one.
  const hasPlan = data?.util != null;
  const color = hasPlan ? loadColor(data!.util) : "#8E9AAB";
  const width = hasPlan ? 2.5 + 6 * Math.min(data!.util!, 1.5) : 2.5;
  return (
    <>
      {/* A faint purple glow under the line when it is selected, then the line itself */}
      {selected && <BaseEdge id={`${id}-sel`} path={path} style={{ stroke: "#4B3FD1", strokeWidth: width + 6, opacity: 0.25 }} />}
      <BaseEdge id={id} path={path} style={{ stroke: color, strokeWidth: width, strokeLinecap: "round" }} />
      {/* One way routes get two arrowheads along the line, either side of the label, pointing the allowed way */}
      {data?.oneWay && [0.32, 0.68].map((f) => {
        const angle = (Math.atan2(b.y - a.y, b.x - a.x) * 180) / Math.PI;
        const size = 5 + width * 0.6;
        return (
          <path key={f} d={`M ${-size} ${-size} L ${size} 0 L ${-size} ${size} Z`} fill={color}
            stroke="#fff" strokeWidth={1.5} strokeLinejoin="round"
            transform={`translate(${a.x + (b.x - a.x) * f} ${a.y + (b.y - a.y) * f}) rotate(${angle})`} />
        );
      })}
      {/* The small label in the middle of the line */}
      <EdgeLabelRenderer>
        <div className="nodrag nopan num pointer-events-auto absolute rounded-[2px] border border-line bg-white/95 px-1.5 py-px text-[10.5px] text-ink"
          style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}>
          {hasPlan
            ? <><b style={{ color: data!.util! > 1 ? "#7A1F3D" : undefined }}>{data!.load}</b> / {data!.capacity}</>
            : <>{data?.capacity} cap, {data?.length} m{data?.travelTime != null && <b className="font-semibold">, {data.travelTime} s</b>}</>}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}

// Tells the map library which drawing to use for each kind of box and line.
const nodeTypes = { place: PlaceNodeView, exit: ExitNodeView };
const edgeTypes = { route: RouteEdgeView };

// What the map is given: the places and routes, whether editing is allowed,
// the plan loads to colour in, and actions to call when the user moves or links things.
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

// Draws the full venue map with a grid background and zoom buttons.
// Editing (dragging, linking, selecting, deleting with the keyboard) is switched on only when allowed.
export default function VenueCanvas({
  nodes, edges, editable = false, loads, onNodesChange, onEdgesChange, onConnect, className,
}: Props) {
  // Overlay the plan's loads without touching the editable state.
  const shownNodes = useMemo(() => nodes.map((n) => {
    const l = n.data.locationType === "exit" ? loads?.exits.get(n.data.name) : undefined;
    return { ...n, data: { ...n.data, editable, load: l?.load, util: l?.util } };
  }), [nodes, loads, editable]);
  // When a plan is shown, routes it does not use get a load of zero, so they appear as unused.
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
        // Editing switches: dragging, linking, selecting and the Delete key only work in the Lab.
        nodesDraggable={editable}
        nodesConnectable={editable}
        elementsSelectable={editable}
        deleteKeyCode={editable ? ["Backspace", "Delete"] : null}
        connectionLineStyle={{ stroke: "#4B3FD1", strokeWidth: 2 }}
        // Zoom to fit the whole venue when it first appears, with a little margin, and limit zooming.
        fitView
        fitViewOptions={{ padding: 0.18 }}
        minZoom={0.3}
        maxZoom={2}
        proOptions={{ hideAttribution: false }}
      >
        {/* Light grid lines behind the map, and zoom buttons in the bottom right corner */}
        <Background variant={BackgroundVariant.Lines} gap={28} color="#E4E9EF" />
        <Controls showInteractive={false} position="bottom-right" />
      </ReactFlow>
    </div>
  );
}
