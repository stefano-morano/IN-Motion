/**
 * particelle.js — setup Three.js per 13.664 particelle con fusione additiva.
 *
 * Equivalente del render pipeline di face_render + face_mat in TD:
 * THREE.Points con AdditiveBlending e colori per vertice.
 */

import * as THREE from 'three';
import { PostProcessing } from './post.js';
import { larghezzaMondo, altezzaMondo } from './scena.js';

// Quanto e' grande una particella, in pixel — ed e' la leva vera sulla
// luminosita', molto piu' del bagliore: in fusione additiva la luce la fa la
// SOVRAPPOSIZIONE, e l'area cresce col quadrato.
//
// Il valore e' in pixel LOGICI e viene moltiplicato per il pixel ratio, cosi'
// l'immagine e' la stessa sul portatile e sul proiettore. Attenzione pero' a
// come si legge il numero: su uno schermo Retina il ratio e' 2, quindi 2 qui
// significa 4 pixel reali di lato — SEDICI volte l'area di prima, quando ogni
// particella era clampata a un pixel solo. La luminosita' cresce col quadrato,
// e i primi tentativi (3, poi 2) erano entrambi troppo per questo.
//
// Si gira anche dall'indirizzo, per tarare senza toccare il file:
//   ?particelle=1.0    piu' vicino alla polvere spenta
//   ?particelle=1.6    piu' vicino alla luce piena
const DIMENSIONE_PARTICELLA = 1.0;

// Una manopola letta dall'indirizzo: ?particelle=2.4&esposizione=1.2
// Serve a tarare la resa sul proiettore vero. Trovati i numeri, si scrivono
// nelle costanti qui sopra: il parametro e' per provare, non per l'opera.
//
// E' ripetuta anche in renderer/post.js, e la ripetizione e' voluta. Metterla in comune in
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

export class RendererParticelle {
    constructor(canvas) {
        // Renderer WebGL
        this._renderer = new THREE.WebGLRenderer({
            canvas,
            antialias: false,
            powerPreference: 'high-performance',
        });
        this._renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        this._renderer.toneMapping = THREE.NoToneMapping;
        this._renderer.setClearColor(0x000000, 1);

        // Scena
        this._scene = new THREE.Scene();

        // Camera ortografica: frustum adattato al rapporto d'aspetto della finestra
        const hw = larghezzaMondo() / 2;
        const hh = altezzaMondo() / 2;
        this._camera = new THREE.OrthographicCamera(-hw, hw, hh, -hh, -10, 10);

        // Geometria particelle
        const n = 13664;
        this._geo = new THREE.BufferGeometry();
        this._posArr = new Float32Array(n * 3);
        this._colArr = new Float32Array(n * 3);
        // Inizializza in posizione zero con colore neutro
        this._geo.setAttribute('position', new THREE.BufferAttribute(this._posArr, 3));
        this._geo.setAttribute('color',    new THREE.BufferAttribute(this._colArr, 3));

        // Materiale: fusione additiva senza depth test.
        //
        // sizeAttenuation e' FALSE, e non e' un dettaglio. Lo shader dei punti
        // di Three.js applica l'attenuazione solo con una camera PROSPETTICA;
        // la nostra e' ortografica, quindi veniva ignorata e 'size' non era
        // in unita' di mondo ma direttamente in pixel. Con size 0.021 la GPU
        // alzava al minimo e ogni particella era UN PIXEL: misurato, 0.021 e
        // 1.0 davano immagini identiche — stessa luminanza media, stessa
        // percentuale di pixel accesi. L'opera rendeva circa un ottavo della
        // luce che doveva, e nessuna manopola di esposizione poteva
        // recuperarlo, perche' schiariva puntini isolati invece di farli
        // sovrapporre. In fusione additiva e' la SOVRAPPOSIZIONE che fa la
        // luce: qui sta la differenza con le particelle di TouchDesigner, che
        // sono geometria vera e coprono piu' pixel ciascuna.
        //
        // Dichiarandolo false, size e' in pixel e lo diciamo apposta. Va
        // moltiplicato per il pixel ratio, altrimenti su uno schermo Retina le
        // particelle coprirebbero meta' della superficie che coprono sul
        // proiettore, e l'opera sarebbe piu' spenta proprio dove si lavora.
        const mat = new THREE.PointsMaterial({
            size: daIndirizzo('particelle', DIMENSIONE_PARTICELLA) * this._renderer.getPixelRatio(),
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

        // Post-processing (bloom + vignetta + grana)
        // Usa window.innerWidth/Height: getBoundingClientRect() può restituire
        // 0 prima che il browser abbia calcolato il layout CSS.
        const w = window.innerWidth  || 1280;
        const h = window.innerHeight || 720;
        this._post = new PostProcessing(this._renderer, this._scene, this._camera, w, h);

        // Dissolvenza iniziale: il renderer parte nero, si accende con accendi()
        this._t_accendi = null;
        this._durata_accendi = 3.0;
        this._post.luminosita = 0;

        // Risponde al resize
        this._onResize = this._onResize.bind(this);
        window.addEventListener('resize', this._onResize);
        this._onResize();
    }

    // ---------------------------------------------------------------- API
    /** Aggiorna posizioni e colori delle particelle. */
    aggiorna(posizioni, colori) {
        if (!posizioni || !colori) return;
        this._posArr.set(posizioni);
        this._colArr.set(colori);
        this._geo.attributes.position.needsUpdate = true;
        this._geo.attributes.color.needsUpdate = true;
    }

    /** Disegna il frame con post-processing. */
    render(tempo) {
        // Gestisce la dissolvenza d'apertura
        if (this._t_accendi !== null) {
            const t = Math.min((tempo - this._t_accendi) / this._durata_accendi, 1);
            this._post.luminosita = Math.pow(t, 2.2);
            if (t >= 1) this._t_accendi = null;
        }
        this._post.render(tempo);
    }

    /** Il colore dell'alone di sfondo, che segue la tinta della sessione. */
    sfondo(rgb) {
        if (this._post) this._post.setSfondo(rgb);
    }

    buio() {
        this._post.luminosita = 0;
        this._t_accendi = null;
    }

    accendi(durata = 3.0, ora = performance.now() / 1000) {
        this._durata_accendi = durata;
        this._t_accendi = ora;
    }

    // ---------------------------------------------------------------- interno
    _onResize() {
        const w = window.innerWidth;
        const h = window.innerHeight;
        this._renderer.setSize(w, h);
        this._post.setSize(w, h);
        // spostando la finestra fra il portatile e il proiettore il pixel
        // ratio cambia: senza questo, le particelle cambierebbero dimensione
        if (this._mat) {
            this._mat.size = daIndirizzo('particelle', DIMENSIONE_PARTICELLA) * this._renderer.getPixelRatio();
        }
        const hw = larghezzaMondo() / 2;
        const hh = altezzaMondo() / 2;
        this._camera.left   = -hw;
        this._camera.right  =  hw;
        this._camera.top    =  hh;
        this._camera.bottom = -hh;
        this._camera.updateProjectionMatrix();
    }
}
