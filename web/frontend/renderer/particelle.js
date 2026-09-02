/**
 * particelle.js — setup Three.js per 13.664 particelle con fusione additiva.
 *
 * Equivalente del render pipeline di face_render + face_mat in TD:
 * THREE.Points con AdditiveBlending e colori per vertice.
 */

import * as THREE from 'three';
import { PostProcessing } from './post.js';
import { altezzaMondo, aspettoSchermo, CAM_TZ } from './scena.js';

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

        // Camera PROSPETTICA, come quella di TouchDesigner.
        //
        // Con una ortografica tutte le particelle hanno la stessa dimensione a
        // qualunque profondita': 'sizeAttenuation' non ha alcun effetto e la
        // nuvola si appiattisce in un adesivo. Con la prospettiva, quelle piu'
        // vicine sono davvero piu' grandi — ed e' cio' che si leggeva come
        // volume nella versione TD.
        //
        // Il fov verticale e' scelto perche' a z=0 l'inquadratura resti
        // IDENTICA a quella ortografica di prima (altezza visibile = SCALA):
        // volto, scritte e mandala restano dove sono, cambia solo cio' che sta
        // davanti o dietro quel piano.
        const fov = 2 * Math.atan(altezzaMondo() / (2 * CAM_TZ)) * 180 / Math.PI;
        this._camera = new THREE.PerspectiveCamera(fov, aspettoSchermo(), 0.1, 100);
        this._camera.position.set(0, 0, CAM_TZ);

        // Geometria particelle
        const n = 13664;
        this._geo = new THREE.BufferGeometry();
        this._posArr = new Float32Array(n * 3);
        this._colArr = new Float32Array(n * 3);
        // Inizializza in posizione zero con colore neutro
        this._geo.setAttribute('position', new THREE.BufferAttribute(this._posArr, 3));
        this._geo.setAttribute('color',    new THREE.BufferAttribute(this._colArr, 3));

        // Materiale: fusione additiva senza depth test
        const mat = new THREE.PointsMaterial({
            // un pelo piu' grandi che nel primo porting: con la prospettiva
            // quelle lontane rimpiccioliscono, e a 0.021 sparivano
            size: 0.026,
            vertexColors: true,
            blending: THREE.AdditiveBlending,
            depthTest: false,
            depthWrite: false,
            transparent: true,
            sizeAttenuation: true,
        });

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
        this._camera.aspect = aspettoSchermo();
        this._camera.fov = 2 * Math.atan(altezzaMondo() / (2 * CAM_TZ)) * 180 / Math.PI;
        this._camera.updateProjectionMatrix();
    }
}
