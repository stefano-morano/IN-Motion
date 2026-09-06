/**
 * post.js — catena di post-produzione con Three.js.
 *
 * Equivalente di td_estetica.py:
 *   render → bloom → (+ sfondo) → vignetta → grana → uscita
 */

import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass }      from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { ShaderPass }      from 'three/addons/postprocessing/ShaderPass.js';

// ------------------------------------------------------------------ shader vignetta + sfondo
const VignettaSfondoShader = {
    uniforms: {
        tDiffuse: { value: null },
        intensita: { value: 0.45 },
        // sfondo: alone radiale al centro (come rampTOP circular)
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
        uniform vec3 sfondoCentro;
        uniform vec3 sfondoBordo;
        varying vec2 vUv;
        void main() {
            vec4 c = texture2D(tDiffuse, vUv);
            vec2 d = vUv * 2.0 - 1.0;
            float r = dot(d, d);                       // 0 al centro, ~2 agli angoli
            // sfondo radiale
            vec3 sfondo = mix(sfondoCentro, sfondoBordo, clamp(r * 0.5, 0.0, 1.0));
            // aggiunge (fusione additiva come in TD)
            vec3 composito = c.rgb + sfondo;
            // vignetta: moltiplica
            float vign = 1.0 - r * intensita;
            gl_FragColor = vec4(composito * clamp(vign, 0.3, 1.0), 1.0);
        }
    `,
};

// ------------------------------------------------------------------ shader grana
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

// ------------------------------------------------------------------ classe
export class PostProcessing {
    constructor(renderer, scene, camera, w, h) {
        this._renderer = renderer;
        this._composer = new EffectComposer(renderer);

        const renderPass = new RenderPass(scene, camera);
        this._composer.addPass(renderPass);

        // Bloom: trasforma puntini → luce (come bloomTOP in TD)
        const bloom = new UnrealBloomPass(
            new THREE.Vector2(w, h),
            0.85,   // intensità
            0.10,   // raggio minimo
            0.28    // soglia
        );
        this._composer.addPass(bloom);

        // Sfondo radiale + vignetta
        this._vignettePass = new ShaderPass(VignettaSfondoShader);
        this._composer.addPass(this._vignettePass);

        // Grana cinematografica
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

    /** Dissolvenza in entrata: 0 = nero, 1 = piena luce. */
    set luminosita(v) {
        this._vignettePass.uniforms.intensita.value = 0.45 * v;
        const f = Math.max(v * 2 - 1, 0);
        this._granaPass.uniforms.ampiezza.value = 0.010 * f;
    }
}
