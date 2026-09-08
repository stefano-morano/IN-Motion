/**
 * post.js — post-production chain with Three.js.
 *
 * Equivalent of td_estetica.py:
 *   render → bloom → (+ background) → vignette → grain → output
 */

import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass }      from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { ShaderPass }      from 'three/addons/postprocessing/ShaderPass.js';

// ------------------------------------------------------------------ how much is visible
// Bloom is the piece that turns dots into light: without it, particles stay
// grains and text is hard to read.
//
// Intensity and threshold match TouchDesigner's bloomTOP, and they are fine
// AS THEY ARE. Worth writing why, because for a while they were forced up to
// 2.10 trying to recover an image that was too dark, and that attempt was the
// wrong cure for the right disease.
//
// The image was dark because of PARTICLE SIZE, not bloom: they were one pixel
// wide (see the note in particelle.js), so they did not overlap and in
// additive blending there was nothing to add. Raising bloom brightened
// isolated dots; measured, the same scene went from 0.01% to 38% burned
// pixels and became a white blotch. With size corrected, these numbers go
// back to TD's.
//
// RADIUS stays different, and that is a real translation error: in TD bloom
// has two radii (min 0.10, max 0.62); UnrealBloomPass has only one, which is
// not a minimum but the WIDTH of the halo. It had been given 0.10.
const BLOOM_INTENSITA = 0.55;   // lowered: at 0.85 face and text were burning
const BLOOM_RAGGIO    = 0.55;
const BLOOM_SOGLIA    = 0.32;   // slightly more selective: less halo on mid pixels

// How exposed the finished image is. A LOOK knob, not a color one, and it
// lives here on purpose: the palette is shared word-for-word with the other
// two versions of the piece, while how bright a pixel comes out depends on
// this chain, which in TD is other nodes. Raise it if the projector looks
// dark, lower it if dense areas burn to white.
const ESPOSIZIONE = 0.72;

// A knob read from the URL: ?particelle=2.4&esposizione=1.2
// Used to calibrate look on the real projector. Once the numbers are found,
// write them into the constants above: the query param is for trying, not
// for the piece.
//
// Also duplicated in renderer/particelle.js, and the duplication is intentional.
// Sharing it in scena.js looked cleaner and turned out to be a hole: the
// browser caches modules and does not revalidate them, so an old copy of
// scena.js without that export was enough for the import to fail, app.js to
// NEVER start, and the UI to leave every button inert — with no on-screen
// error. Six repeated lines cost less than that symptom.
function fromQuery(nome, predefinito) {
    try {
        const v = parseFloat(new URLSearchParams(location.search).get(nome));
        return Number.isFinite(v) && v > 0 ? v : predefinito;
    } catch (_) {
        return predefinito;
    }
}

// ------------------------------------------------------------------ vignette + background shader
const VignettaSfondoShader = {
    uniforms: {
        tDiffuse: { value: null },
        intensita: { value: 0.45 },
        esposizione: { value: 1.0 },
        // background: radial halo at the center (like rampTOP circular).
        // The two colors are no longer fixed: they follow the session tint,
        // see setSfondo(). These remain the starting-blue values.
        sfondoCentro: { value: new THREE.Color(0.030, 0.042, 0.085) },
        sfondoBordo:  { value: new THREE.Color(0.004, 0.006, 0.016) },
    },
    vertexShader: `
        varying vec2 vUv;
        void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }
    `,
    fragmentShader: `
        uniform sampler2D tDiffuse;
        uniform float intensita;
        uniform float esposizione;
        uniform vec3 sfondoCentro;
        uniform vec3 sfondoBordo;
        varying vec2 vUv;
        void main() {
            vec4 c = texture2D(tDiffuse, vUv);
            vec2 d = vUv * 2.0 - 1.0;
            float r = dot(d, d);                       // 0 at center, ~2 at corners
            // radial background
            vec3 sfondo = mix(sfondoCentro, sfondoBordo, clamp(r * 0.5, 0.0, 1.0));
            // add (additive blend as in TD)
            vec3 composito = (c.rgb + sfondo) * esposizione;
            // vignette: multiply
            float vign = 1.0 - r * intensita;
            gl_FragColor = vec4(composito * clamp(vign, 0.3, 1.0), 1.0);
        }
    `,
};

// ------------------------------------------------------------------ grain shader
const GranaShader = {
    uniforms: {
        tDiffuse: { value: null },
        tempo:    { value: 0.0 },
        ampiezza: { value: 0.010 },
    },
    vertexShader: `
        varying vec2 vUv;
        void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }
    `,
    fragmentShader: `
        uniform sampler2D tDiffuse;
        uniform float tempo;
        uniform float ampiezza;
        varying vec2 vUv;
        float rand(vec2 co) {
            return fract(sin(dot(co, vec2(12.9898, 78.233))) * 43758.5453);
        }
        void main() {
            vec4 c = texture2D(tDiffuse, vUv);
            float grain = rand(vUv + vec2(tempo)) - 0.5;
            gl_FragColor = vec4(c.rgb + grain * ampiezza, c.a);
        }
    `,
};

// ------------------------------------------------------------------ class
export class PostProcessing {
    constructor(renderer, scene, camera, w, h) {
        this._renderer = renderer;
        this._composer = new EffectComposer(renderer);

        const renderPass = new RenderPass(scene, camera);
        this._composer.addPass(renderPass);

        // Bloom: the piece that turns dots into light.
        const bloom = new UnrealBloomPass(
            new THREE.Vector2(w, h),
            fromQuery('bagliore', BLOOM_INTENSITA), BLOOM_RAGGIO, BLOOM_SOGLIA
        );
        this._composer.addPass(bloom);

        // Radial background + vignette
        this._vignettePass = new ShaderPass(VignettaSfondoShader);
        this._vignettePass.uniforms.esposizione.value =
            fromQuery('esposizione', ESPOSIZIONE);
        this._composer.addPass(this._vignettePass);

        // Film grain
        this._granaPass = new ShaderPass(GranaShader);
        this._granaPass.renderToScreen = true;
        this._composer.addPass(this._granaPass);
    }

    render(tempo) {
        this._granaPass.uniforms.tempo.value = tempo * 0.1 % 1.0;
        this._composer.render();
    }

    setSize(w, h) {
        this._composer.setSize(w, h);
    }

    /** Fade in: 0 = black, 1 = full light. */
    set brightness(v) {
        this._vignettePass.uniforms.intensita.value = 0.45 * v;
        const f = Math.max(v * 2 - 1, 0);
        this._granaPass.uniforms.ampiezza.value = 0.010 * f;
    }

    /**
     * Background halo color. Center and edge are not two independent colors:
     * the edge is exactly 0.188 of the center, which is the ratio of the
     * original blue on the blue channel — the one that decides at those
     * luminances. So the gradient carries the SHAPE of the halo and this
     * method carries its COLOR, like the two separate nodes inside TD.
     */
    setSfondo(rgb) {
        if (!rgb) return;
        this._vignettePass.uniforms.sfondoCentro.value.setRGB(rgb[0], rgb[1], rgb[2]);
        this._vignettePass.uniforms.sfondoBordo.value.setRGB(
            rgb[0] * 0.188, rgb[1] * 0.188, rgb[2] * 0.188);
    }
}
