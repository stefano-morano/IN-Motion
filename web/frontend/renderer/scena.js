/**
 * scena.js — shared world coordinates for logic, text, and the renderer.
 *
 * Aspect ratio follows the window (as in td_face_points.py with
 * render.par.resolutionw / resolutionh), so face and text do not
 * distort on non-16:9 screens.
 */

export const SCALE = 2.45;

export const TEXT_WIDTH = 2.33;
export const TEXT_HEIGHT   = 1.10;

export const CAM_TX = 0.0;
export const CAM_TY = 0.0;

export const MANDALA_FILL = 0.88;

export function screenAspect() {
    const w = window.innerWidth  || 1280;
    const h = window.innerHeight || 720;
    return w / h;
}

export function worldWidth() {
    return screenAspect() * SCALE;
}

export function worldHeight() {
    return SCALE;
}

export function visibleRadius() {
    return (SCALE / 2.0) * MANDALA_FILL;
}
