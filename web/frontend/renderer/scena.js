/**
 * scena.js — coordinate mondo condivise tra logica, testo e renderer.
 *
 * Il rapporto d'aspetto segue la finestra (come in td_face_points.py con
 * render.par.resolutionw / resolutionh), così volto e scritte non si
 * deformano su schermi non 16:9.
 */

export const SCALA = 2.45;

export const TESTO_LARGHEZZA = 2.33;
export const TESTO_ALTEZZA   = 1.10;

export const CAM_TX = 0.0;
export const CAM_TY = 0.0;

export const MANDALA_RIEMPIMENTO = 0.88;

export function aspettoSchermo() {
    const w = window.innerWidth  || 1280;
    const h = window.innerHeight || 720;
    return w / h;
}

export function larghezzaMondo() {
    return aspettoSchermo() * SCALA;
}

export function altezzaMondo() {
    return SCALA;
}

export function raggioVisibile() {
    return (SCALA / 2.0) * MANDALA_RIEMPIMENTO;
}
