import type { ReactNode } from "react";

/**
 * Horizontal swipe carousel on mobile (conserves vertical space, per
 * designdoc.md); becomes a real grid at desktop widths so the web-app view
 * isn't just a stretched mobile column with wasted space.
 */
export function Carousel({ children }: { children: ReactNode }) {
  return (
    <div className="-mx-4 flex snap-x snap-mandatory gap-3 overflow-x-auto scrollbar-none px-4 pb-2 lg:mx-0 lg:grid lg:grid-cols-4 lg:overflow-visible lg:px-0 lg:pb-0">
      {children}
    </div>
  );
}

export function CarouselItem({ children }: { children: ReactNode }) {
  return (
    <div className="w-[78%] shrink-0 snap-start sm:w-[320px] lg:w-auto">
      {children}
    </div>
  );
}
