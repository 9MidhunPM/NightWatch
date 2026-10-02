export type ShowcaseController = {
  progress: number;
  pointerX: number;
  pointerY: number;
  subscribe: (listener: () => void) => () => void;
  update: (values: Partial<Pick<ShowcaseController, 'progress' | 'pointerX' | 'pointerY'>>) => void;
};

export function createShowcaseController(): ShowcaseController {
  const listeners = new Set<() => void>();
  return {
    progress: 0, pointerX: 0, pointerY: 0,
    subscribe(listener) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    update(values) { Object.assign(this, values); for (const listener of listeners) listener(); },
  };
}
