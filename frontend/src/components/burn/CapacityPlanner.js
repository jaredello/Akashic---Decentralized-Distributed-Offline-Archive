/**
 * Disc capacity planner: how full each 100 GB disc is and roughly how many more items would fit.
 */
import React from "react";
import { Gauge, AlertTriangle } from "lucide-react";
import { fmtBytes } from "@/lib/api";

const DiscPlan = ({ label, color, unit, used, plan }) => {
  const fill = Math.max(plan?.fill_pct || 0, used > 0 ? 0.4 : 0);
  return (
    <div className="border border-[#eaecf0] rounded-sm p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="wiki-serif text-base" style={{ color }}>{label}</span>
        <span className="mono text-[11px] text-[#72777d]">{fmtBytes(used)} used</span>
      </div>
      <div className="h-2 bg-[#eaecf0] rounded-full overflow-hidden mb-1">
        <div className="h-full rounded-full" style={{ width: `${Math.min(fill, 100)}%`, background: color }} />
      </div>
      <div className="mono text-[10px] text-[#9aa0a6] mb-3">{(plan?.fill_pct ?? 0).toFixed(4)}% of 100 GB</div>
      <dl className="text-sm space-y-1.5">
        <div className="flex justify-between"><dt className="text-[#54595d]">Avg per {unit.slice(0, -1)}</dt><dd className="mono">{fmtBytes(plan?.avg_item_bytes || 0)}</dd></div>
        <div className="flex justify-between"><dt className="text-[#54595d]">Fits per disc</dt><dd className="mono font-bold" style={{ color }}>~{(plan?.est_items_per_disc || 0).toLocaleString()} {unit}</dd></div>
        <div className="flex justify-between"><dt className="text-[#54595d]">Headroom left</dt><dd className="mono">~{(plan?.headroom_items || 0).toLocaleString()} more</dd></div>
      </dl>
    </div>
  );
};

export const CapacityPlanner = ({ status }) => {
  const cap = status?.capacity;
  const overCapacity = cap && (cap.text.over_capacity || cap.media.over_capacity || cap.largest_media_over_disc);
  return (
    <section className="mt-8 border border-[#c8ccd1] rounded-sm p-5" data-testid="capacity-planner">
      <div className="flex items-center gap-2 mb-1">
        <Gauge size={17} className="text-[#3366cc]" />
        <h2 className="wiki-serif text-xl text-[#000]">Disc capacity planner</h2>
      </div>
      <p className="text-sm text-[#54595d] mb-4">
        Estimated how much each 100 GB M-DISC can hold at the current average item size.
      </p>
      {overCapacity && (
        <div className="flex items-center gap-2 text-sm text-[#dd3333] bg-[#fdeaea] border border-[#f3b5b5] rounded-sm px-3 py-2 mb-4" data-testid="capacity-warning">
          <AlertTriangle size={15} /> A disc has exceeded its 100 GB capacity — remove items before burning.
        </div>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <DiscPlan label="Text Disc" color="#15803d" unit="articles" used={status?.text_disk?.used_bytes || 0} plan={cap?.text} />
        <DiscPlan label="Media Disc" color="#b45309" unit="images" used={status?.media_disk?.used_bytes || 0} plan={cap?.media} />
      </div>
    </section>
  );
};
