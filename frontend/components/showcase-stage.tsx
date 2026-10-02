'use client';

import { Component, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import dynamic from 'next/dynamic';
import Image from 'next/image';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { useGSAP } from '@gsap/react';
import { createShowcaseController } from '@/lib/showcase-motion';

gsap.registerPlugin(ScrollTrigger, useGSAP);
const Scene = dynamic(() => import('@/components/showcase-scene'), { ssr: false });

class SceneBoundary extends Component<{ children: ReactNode; onError: () => void }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch() { this.props.onError(); }
  render() { return this.state.failed ? null : this.props.children; }
}

export function ShowcaseStage() {
  const root = useRef<HTMLDivElement>(null);
  const [enabled, setEnabled] = useState(false);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [chapter, setChapter] = useState(0);
  const controller = useMemo(() => createShowcaseController(), []);
  const onReady = useCallback(() => setReady(true), []);
  const onError = useCallback(() => { setFailed(true); setReady(false); }, []);

  useEffect(() => {
    const media = window.matchMedia('(min-width: 1024px) and (pointer: fine) and (prefers-reduced-motion: no-preference)');
    const update = () => {
      let supported = false;
      if (media.matches) {
        try {
          const probe = document.createElement('canvas');
          const context = probe.getContext('webgl2');
          supported = Boolean(context);
          context?.getExtension('WEBGL_lose_context')?.loseContext();
        } catch { supported = false; }
      }
      setEnabled(media.matches && supported);
      setFailed(media.matches && !supported);
      if (!media.matches || !supported) setReady(false);
    };
    update(); media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);

  useEffect(() => {
    if (!enabled || ready || failed) return;
    const timeout = window.setTimeout(onError, 15000);
    return () => window.clearTimeout(timeout);
  }, [enabled, ready, failed, onError]);

  useGSAP(() => {
    if (!enabled) return;
    const theatre = document.getElementById('theatre');
    if (!theatre) return;
    let visible = true;
    const notify = () => {
      if (visible && !document.hidden) controller.update({ progress: controller.progress });
      const next = Math.min(5, Math.floor(controller.progress * 6));
      setChapter(current => current === next ? current : next);
    };
    gsap.to(controller, { progress: 1, ease: 'none', scrollTrigger: { trigger: theatre, start: 'top top', end: 'bottom bottom', scrub: 0.55, invalidateOnRefresh: true }, onUpdate: notify });
    const observer = new IntersectionObserver(entries => { visible = entries[0].isIntersecting; if (visible) notify(); });
    observer.observe(theatre);
    let pointerFrame = 0;
    const pointer = (event: PointerEvent) => {
      if (pointerFrame || document.hidden || !visible) return;
      const x = event.clientX, y = event.clientY;
      pointerFrame = requestAnimationFrame(() => {
        controller.update({ pointerX: (x / window.innerWidth - 0.5) * 2, pointerY: (y / window.innerHeight - 0.5) * 2 });
        pointerFrame = 0;
      });
    };
    const visibility = () => { if (!document.hidden) notify(); };
    theatre.addEventListener('pointermove', pointer, { passive: true });
    document.addEventListener('visibilitychange', visibility);
    return () => { observer.disconnect(); cancelAnimationFrame(pointerFrame); theatre.removeEventListener('pointermove', pointer); document.removeEventListener('visibilitychange', visibility); controller.update({ progress: 0, pointerX: 0, pointerY: 0 }); };
  }, { scope: root, dependencies: [enabled, controller], revertOnUpdate: true });

  return <div ref={root} className="nw-stage-viewport" data-scene-ready={ready && enabled && !failed} aria-hidden="true">
    <div className="nw-scene-region">
      <Image className="nw-scene-poster" src="/showcase/islands-poster.webp" alt="" width={1536} height={1024} sizes="(max-width: 1023px) 100vw, 75vw" preload/>
      {enabled && !failed && <div className="nw-canvas"><SceneBoundary onError={onError}><Scene controller={controller} onReady={onReady} onError={onError}/></SceneBoundary></div>}
      <div className="nw-stage-vignette"/>
      <div className="nw-scene-caption"><span className={'nw-state-dot ' + (chapter > 0 && chapter < 4 ? 'is-warning' : '')}/><span>{chapter === 0 ? 'An illustrative infrastructure world' : 'Representative incident simulation'}</span><span className="nw-scene-caption-end">{failed ? 'Scene poster' : 'Scroll to explore'}</span></div>
    </div>
  </div>;
}
