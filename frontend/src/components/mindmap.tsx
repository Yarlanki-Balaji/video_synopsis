"use client";

import { useEffect, useRef } from "react";

// Strip an accidental ```...``` fence the model might wrap the outline in.
function clean(md: string): string {
  const t = md.trim();
  if (t.startsWith("```")) {
    return t.replace(/^```[a-zA-Z]*\n?/, "").replace(/\n?```$/, "").trim();
  }
  return t;
}

/**
 * Renders a markdown outline (# root, ## branches, nested bullets) as an
 * interactive mind map via markmap. Client-only; markmap is imported lazily so
 * it never touches the server render. Drawn on a light canvas so the default
 * dark node text stays readable in both themes.
 */
export function MindMap({ markdown }: { markdown: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    let mm: { destroy?: () => void } | undefined;
    let cancelled = false;
    (async () => {
      const [{ Transformer }, { Markmap }] = await Promise.all([
        import("markmap-lib"),
        import("markmap-view"),
      ]);
      if (cancelled || !svgRef.current) return;
      // markmap's autoFit reads the SVG's width/height as SVGLength values. A relative
      // CSS width (w-full = 100%) makes that throw "Could not resolve relative length",
      // so give the SVG ABSOLUTE pixel attributes first; CSS still scales the display.
      const w = Math.max(320, containerRef.current?.clientWidth || 800);
      svgRef.current.setAttribute("width", String(w));
      svgRef.current.setAttribute("height", "460");
      const { root } = new Transformer().transform(clean(markdown) || "# (empty)");
      svgRef.current.innerHTML = "";
      try {
        mm = Markmap.create(svgRef.current, { autoFit: true, duration: 300, paddingX: 16 }, root);
      } catch {
        // Defensive: a mindmap render must never crash the page.
      }
    })();
    return () => {
      cancelled = true;
      mm?.destroy?.();
    };
  }, [markdown]);

  return (
    <div ref={containerRef} className="overflow-hidden rounded-lg border border-border bg-[#fbfaf9]">
      <svg ref={svgRef} className="h-[460px] w-full" aria-label="Mind map" />
    </div>
  );
}
