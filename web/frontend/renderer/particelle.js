/**
 * particelle.js — Three.js setup for 13,664 particles with additive blending.
 *
 * Equivalent of the face_render + face_mat render pipeline in TD:
 * THREE.Points with AdditiveBlending and per-vertex colors.
 */

import * as THREE from 'three';
import { PostProcessing } from './post.js';
import { worldWidth, worldHeight } from './scena.js';

// How large a particle is, in pixels — and it is the real lever on
// brightness, much more than bloom: in additive blending light comes from
// OVERLAP, and area grows with the square.
//
// The value is in LOGICAL pixels and is multiplied by the pixel ratio, so
// the image is the same on a laptop and on the projector. Be careful how
// you read the number though: on a Retina screen the ratio is 2, so 2 here
// means 4 real pixels on a side — SIXTEEN times the earlier area, when each
// particle was clamped to a single pixel. Brightness grows with the square,
// and the first attempts (3, then 2) were both too much for that reason.
//
// Also tunable from the URL, to calibrate without touching the file:
//   ?particelle=1.0    closer to full light (previous value)
//   ?particelle=0.7    closer to dust, more readable shapes
const DIMENSIONE_PARTICELLA = 0.75;

// A knob read from the URL: ?particelle=2.4&esposizione=1.2
// Used to calibrate look on the real projector. Once the numbers are found,
// write them into the constants above: the query param is for trying, not
// for the piece.
//
// Also duplicated in renderer/post.js, and the duplication is intentional.
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

export class ParticleRenderer {
    constructor(canvas) {
        // WebGL renderer
        this._renderer = new THREE.WebGLRenderer({
            canvas,
            antialias: false,
            powerPreference: 'high-performance',
        });
        this._renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        this._renderer.toneMapping = THREE.NoToneMapping;
        this._renderer.setClearColor(0x000000, 1);

        // Scene
        this._scene = new THREE.Scene();

        // Orthographic camera: frustum adapted to the window aspect ratio
        const hw = worldWidth() / 2;
        const hh = worldHeight() / 2;
        this._camera = new THREE.OrthographicCamera(-hw, hw, hh, -hh, -10, 10);

        // Particle geometry
        const n = 13664;
        this._geo = new THREE.BufferGeometry();
        this._posArr = new Float32Array(n * 3);
        this._colArr = new Float32Array(n * 3);
        // Initialize at origin with a neutral color
        this._geo.setAttribute('position', new THREE.BufferAttribute(this._posArr, 3));
        this._geo.setAttribute('color',    new THREE.BufferAttribute(this._colArr, 3));

        // Material: additive blending without depth test.
        //
        // sizeAttenuation is FALSE, and that is not a detail. Three.js's
        // points shader applies attenuation only with a PERSPECTIVE camera;
        // ours is orthographic, so it was ignored and 'size' was not in
        // world units but directly in pixels. With size 0.021 the GPU
        // clamped to the minimum and every particle was ONE PIXEL: measured,
        // 0.021 and 1.0 produced identical images — same mean luminance, same
        // percentage of lit pixels. The piece rendered about an eighth of the
        // light it should have, and no exposure knob could recover it, because
        // it brightened isolated dots instead of making them overlap. In
        // additive blending OVERLAP is what makes the light: that is the
        // difference from TouchDesigner particles, which are real geometry and
        // cover more pixels each.
        //
        // Declaring it false, size is in pixels and we mean it. It must be
        // multiplied by the pixel ratio, otherwise on a Retina screen
        // particles would cover half the area they cover on the projector,
        // and the piece would be dimmer exactly where you work.
        const mat = new THREE.PointsMaterial({
            size: fromQuery('particelle', DIMENSIONE_PARTICELLA) * this._renderer.getPixelRatio(),
            vertexColors: true,
            blending: THREE.AdditiveBlending,
            depthTest: false,
            depthWrite: false,
            transparent: true,
            sizeAttenuation: false,
        });
        this._mat = mat;

        const points = new THREE.Points(this._geo, mat);
        this._scene.add(points);

        // Post-processing (bloom + vignette + grain)
        // Use window.innerWidth/Height: getBoundingClientRect() can return
        // 0 before the browser has computed the CSS layout.
        const w = window.innerWidth  || 1280;
        const h = window.innerHeight || 720;
        this._post = new PostProcessing(this._renderer, this._scene, this._camera, w, h);

        // Initial fade: renderer starts black, lights up via lightsUp()
        this._t_accendi = null;
        this._durata_accendi = 3.0;
        this._post.brightness = 0;

        // Respond to resize
        this._onResize = this._onResize.bind(this);
        window.addEventListener('resize', this._onResize);
        this._onResize();
    }

    // ---------------------------------------------------------------- API
    /** Update particle positions and colors. */
    update(posizioni, colori) {
        if (!posizioni || !colori) return;
        this._posArr.set(posizioni);
        this._colArr.set(colori);
        this._geo.attributes.position.needsUpdate = true;
        this._geo.attributes.color.needsUpdate = true;
    }

    /** Draw the frame with post-processing. */
    render(tempo) {
        // Handle the opening fade
        if (this._t_accendi !== null) {
            const t = Math.min((tempo - this._t_accendi) / this._durata_accendi, 1);
            this._post.brightness = Math.pow(t, 2.2);
            if (t >= 1) this._t_accendi = null;
        }
        this._post.render(tempo);
    }

    /** Background halo color, following the session tint. */
    setBackground(rgb) {
        if (this._post) this._post.setSfondo(rgb);
    }

    lightsOut() {
        this._post.brightness = 0;
        this._t_accendi = null;
    }

    lightsUp(durata = 3.0, ora = performance.now() / 1000) {
        this._durata_accendi = durata;
        this._t_accendi = ora;
    }

    // ---------------------------------------------------------------- internal
    _onResize() {
        const w = window.innerWidth;
        const h = window.innerHeight;
        this._renderer.setSize(w, h);
        this._post.setSize(w, h);
        // moving the window between laptop and projector changes the pixel
        // ratio: without this, particles would change size
        if (this._mat) {
            this._mat.size = fromQuery('particelle', DIMENSIONE_PARTICELLA) * this._renderer.getPixelRatio();
        }
        const hw = worldWidth() / 2;
        const hh = worldHeight() / 2;
        this._camera.left   = -hw;
        this._camera.right  =  hw;
        this._camera.top    =  hh;
        this._camera.bottom = -hh;
        this._camera.updateProjectionMatrix();
    }
}
