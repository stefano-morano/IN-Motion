/**
 * particelle.js — setup Three.js per 13.664 particelle con fusione additiva.
 *
 * Equivalente del render pipeline di face_render + face_mat in TD:
 * THREE.Points con AdditiveBlending e colori per vertice.
 */

import * as THREE from 'three';
import { PostProcessing } from './post.js';
import { altezzaMondo, aspettoSchermo, CAM_TZ } from './scena.js';

// Quanti PIXEL DI SCHERMO deve occupare una particella sul piano z=0.
//
// Non e' un capriccio esprimerlo in pixel invece che in unita' di mondo. Con
// la camera prospettica 'size' e' una misura di mondo che viene proiettata,
// quindi la stessa costante da' particelle grandi il doppio su una finestra
// alta il doppio. E in fusione additiva la luce cresce con l'AREA: raddoppiare
// il lato quadruplica la luce, e l'immagine si brucia in bianco.
//
// Prima della camera prospettica il valore in mondo era cosi' piccolo che il
// GPU lo arrotondava a 1 pixel per tutti. Da li' il salto: 4 pixel di lato
// sono 17 volte la luce di un pixel.
// 2.5 px di dischetto morbido emettono circa il 13% di luce in piu' di quel
// singolo pixel pieno di prima (2.5^2 x 0.181 = 1.13): la particella si vede
// due volte e mezzo piu' grande e ha un bordo, senza bruciare l'immagine.
const PIXEL_PARTICELLA = 2.5;

/**
 * Un dischetto morbido, invece del quadrato pieno che PointsMaterial disegna
 * senza texture. Due motivi, e valgono entrambi:
 *  - i quadrati si vedono, e a due pixel di lato sembrano un difetto;
 *  - la luce si concentra al centro e sfuma ai bordi, quindi la somma di due
 *    particelle sovrapposte e' molto piu' bassa di quella di due quadrati.
 *    E' cio' che permette di ingrandirle senza bruciare l'immagine.
 */
function texturaParticella(lato = 64) {
    const c = document.createElement('canvas');
    c.width = c.height = lato;
    const g = c.getContext('2d');
    const r = lato / 2;
    const grad = g.createRadialGradient(r, r, 0, r, r, r);
    grad.addColorStop(0.00, 'rgba(255,255,255,1)');
    grad.addColorStop(0.30, 'rgba(255,255,255,0.62)');
    grad.addColorStop(0.65, 'rgba(255,255,255,0.16)');
    grad.addColorStop(1.00, 'rgba(255,255,255,0)');
    g.fillStyle = grad;
    g.fillRect(0, 0, lato, lato);
    const t = new THREE.CanvasTexture(c);
    t.needsUpdate = true;
    return t;
}

/** La dimensione in unita' di mondo che rende PIXEL_PARTICELLA pixel a z=0. */
function dimensioneMondo() {
    const h = window.innerHeight || 720;
    return 2 * PIXEL_PARTICELLA * CAM_TZ / h;
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
            size: dimensioneMondo(),
            map: texturaParticella(),
            alphaTest: 0.0,
            vertexColors: true,
            blending: THREE.AdditiveBlending,
            depthTest: false,
            depthWrite: false,
            transparent: true,
            sizeAttenuation: true,
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
        // la dimensione si ricalcola: e' fissata in pixel di schermo, non in
        // unita' di mondo, quindi dipende dall'altezza della finestra
        if (this._mat) this._mat.size = dimensioneMondo();
        this._camera.aspect = aspettoSchermo();
        this._camera.fov = 2 * Math.atan(altezzaMondo() / (2 * CAM_TZ)) * 180 / Math.PI;
        this._camera.updateProjectionMatrix();
    }
}
