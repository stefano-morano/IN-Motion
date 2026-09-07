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

// ------------------------------------------------------------------ quanto si vede
// Il bagliore e' il pezzo che trasforma dei puntini in luce: senza, le
// particelle restano granelli e le scritte si leggono a fatica.
//
// Intensita' e soglia sono quelle del bloomTOP di TouchDesigner, e vanno bene
// COSI'. Vale la pena scrivere perche', perche' per un po' sono state alzate a
// forza fino a 2.10 nel tentativo di recuperare un'immagine troppo scura, e
// quel tentativo era la cura sbagliata per la malattia giusta.
//
// L'immagine era scura per la DIMENSIONE DELLE PARTICELLE, non per il
// bagliore: erano larghe un pixel (vedi la nota in particelle.js), quindi non
// si sovrapponevano e in fusione additiva non c'era niente da sommare.
// Alzando il bagliore si schiarivano puntini isolati; misurata, la stessa
// scena passava dallo 0.01% al 38% di pixel bruciati e diventava una macchia
// bianca. Corretta la dimensione, questi numeri tornano quelli di TD.
//
// Il RAGGIO invece resta diverso, ed e' un errore di traduzione vero: in TD il
// bagliore ha due raggi (min 0.10, max 0.62), UnrealBloomPass ne ha uno solo,
// che non e' un minimo ma l'AMPIEZZA dell'alone. Gli era stato passato 0.10.
const BLOOM_INTENSITA = 0.85;   // come bloomintensity in td_estetica.py
const BLOOM_RAGGIO    = 0.62;   // l'ampiezza dell'alone (era 0.10: quasi nulla)
const BLOOM_SOGLIA    = 0.28;   // come bloomthreshold

// Quanto e' esposta l'immagine finita. E' una manopola di RESA, non di colore,
// e sta qui apposta: la palette e' condivisa parola per parola con le altre due
// versioni dell'opera, mentre quanto viene luminoso un pixel dipende da questa
// catena, che in TD e' fatta di altri nodi. Alzala se il proiettore rende
// scuro, abbassala se le zone dense bruciano in bianco.
const ESPOSIZIONE = 1.0;

// Una manopola letta dall'indirizzo: ?particelle=2.4&esposizione=1.2
// Serve a tarare la resa sul proiettore vero. Trovati i numeri, si scrivono
// nelle costanti qui sopra: il parametro e' per provare, non per l'opera.
//
// E' ripetuta anche in renderer/particelle.js, e la ripetizione e' voluta. Metterla in comune in
// scena.js sembrava piu' pulito e si e' rivelato un buco: il browser tiene i
// moduli in cache e non li rivalida, quindi bastava una copia vecchia di
// scena.js senza quell'export perche' l'import fallisse, app.js non partisse
// MAI e l'interfaccia restasse con tutti i pulsanti inerti — senza un errore
// a schermo. Sei righe ripetute costano meno di quel sintomo.
function daIndirizzo(nome, predefinito) {
    try {
        const v = parseFloat(new URLSearchParams(location.search).get(nome));
        return Number.isFinite(v) && v > 0 ? v : predefinito;
    } catch (_) {
        return predefinito;
    }
}

// ------------------------------------------------------------------ shader vignetta + sfondo
const VignettaSfondoShader = {
    uniforms: {
        tDiffuse: { value: null },
        intensita: { value: 0.45 },
        esposizione: { value: 1.0 },
        // sfondo: alone radiale al centro (come rampTOP circular).
        // I due colori non sono piu' fissi: seguono la tinta della sessione,
        // vedi setSfondo(). Questi restano i valori del blu di partenza.
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
            float r = dot(d, d);                       // 0 al centro, ~2 agli angoli
            // sfondo radiale
            vec3 sfondo = mix(sfondoCentro, sfondoBordo, clamp(r * 0.5, 0.0, 1.0));
            // aggiunge (fusione additiva come in TD)
            vec3 composito = (c.rgb + sfondo) * esposizione;
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

        // Bloom: e' il pezzo che trasforma dei puntini in luce.
        const bloom = new UnrealBloomPass(
            new THREE.Vector2(w, h),
            daIndirizzo('bagliore', BLOOM_INTENSITA), BLOOM_RAGGIO, BLOOM_SOGLIA
        );
        this._composer.addPass(bloom);

        // Sfondo radiale + vignetta
        this._vignettePass = new ShaderPass(VignettaSfondoShader);
        this._vignettePass.uniforms.esposizione.value =
            daIndirizzo('esposizione', ESPOSIZIONE);
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

    /**
     * Il colore dell'alone di sfondo. Centro e bordo non sono due colori
     * indipendenti: il bordo e' esattamente 0.188 del centro, che e' il
     * rapporto del blu originale sul canale blu — quello che a quelle
     * luminosita' decide. Cosi' il gradiente porta la FORMA dell'alone e
     * questo metodo ne porta il COLORE, come i due nodi separati dentro TD.
     */
    setSfondo(rgb) {
        if (!rgb) return;
        this._vignettePass.uniforms.sfondoCentro.value.setRGB(rgb[0], rgb[1], rgb[2]);
        this._vignettePass.uniforms.sfondoBordo.value.setRGB(
            rgb[0] * 0.188, rgb[1] * 0.188, rgb[2] * 0.188);
    }
}
