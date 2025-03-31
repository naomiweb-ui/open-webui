# TODO: Implement a more intelligent load balancing mechanism for distributing requests among multiple backend instances.
# Current implementation uses a simple round-robin approach (random.choice). Consider incorporating algorithms like weighted round-robin,
# least connections, or least response time for better resource utilization and performance optimization.

import asyncio
import json
import logging
import os
import random
import re
import time
from typing import Optional, Union
from urllib.parse import urlparse
import aiohttp
from aiocache import cached
import requests
from open_webui.models.users import UserModel

from open_webui.env import (
    ENABLE_FORWARD_USER_INFO_HEADERS,
)

from fastapi import (
    Depends,
    FastAPI,
    File,
    HTTPException,
    Request,
    UploadFile,
    APIRouter,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, validator
from starlette.background import BackgroundTask


from open_webui.models.models import Models
from open_webui.utils.misc import (
    calculate_sha256,
)
from open_webui.utils.payload import (
    apply_model_params_to_body_ollama,
    apply_model_params_to_body_openai,
    apply_model_system_prompt_to_body,
)
from open_webui.utils.auth import get_admin_user, get_verified_user
from open_webui.utils.access_control import has_access


from open_webui.config import (
    UPLOAD_DIR,
)
from open_webui.env import (
    ENV,
    SRC_LOG_LEVELS,
    AIOHTTP_CLIENT_TIMEOUT,
    AIOHTTP_CLIENT_TIMEOUT_MODEL_LIST,
    BYPASS_MODEL_ACCESS_CONTROL,
)
from open_webui.constants import ERROR_MESSAGES

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["OLLAMA"])


##########################################
#
# Utility functions
#
##########################################

# Chunk a document and send it to Ollama for tokenization

def chunk_text(text, chunk_size=512):
    words = text.split()
    return [" ".join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]

url = "http://localhost:11434/api/tokenize"
document = """GUIDE D’INTRODUCTION 
À L’IMAGERIE MÉDICALE : 
UTILISATION ET SÛRETÉ DES RAYONS X
2013
GUIDE D’INTRODUCTION 
À L’IMAGERIE MÉDICALE : 
UTILISATION ET SÛRETÉ DES RAYONS X
Auteurs :
JULIAN DOBRANOWSKI, MD, FRCPCa,b
ALYAA H. ELZIBAK, M. Sc.c,d
ALEXANDER DOBRANOWSKIe
ANTHONY FARFUSe
CHRISTOPHER ASTILLe
ABIRAM NAIRe
ANTHONY LEVINSONf
YOGESH THAKUR, Ph. D., MCCPg
MICHAEL D. NOSEWORTHY, Ph. D., ing.d,h
C’est avec gratitude que la CAR 
souligne la contribution de :
THOR BJARNASON, Ph. D., MCCPMi
pour la révision externe de ce document.
a Service d’imagerie diagnostique, St. Joseph’s Healthcare, Hamilton, Ontario, Canada.
b Professeur clinicien agrégé, McMaster University, Hamilton, Ontario, Canada.
c Département de physique médicale et de sciences appliquées des rayonnements, 
McMaster University, Hamilton, Ontario, Canada.
d
 Imaging Research Centre, St. Joseph’s Healthcare, Hamilton, Ontario, Canada.
e MBBS Program, University of Adelaide, Adelaide, Australie-Méridionale.
f Titulaire de la John Evans Chair in Educational Research, Professeur agrégé, 
McMaster University, Hamilton, Ontario, Canada.
g Service de radiologie, Vancouver Coastal Health Authority, Vancouver, C.-B., Canada.
h Services d’imagerie diagnostique, Interior Health Authority, Kelowna, 
BC Radiology, University of British Columbia, Vancouver, C.-B., Canada.
i Responsable de la radioprotection et de la qualité, Services d’imagerie 
diagnostique, Interior Health Authority, Kelowna, C.-B., Canada. 
1
TABLE DES MATIÈRES
Introduction ...............................................................................................................................................................................................2
1. À propos des rayonnements..................................................................................................................................................3
2. Les rayonnements en imagerie médicale .........................................................................................................................4
3. Rayonnements ionisants : concepts fondamentaux.....................................................................................................7
4. Rayonnements ionisants : protection..............................................................................................................................10
5. Rayonnements ionisants : patientes enceintes ..........................................................................................................12
6. Modalités d’imagerie sans rayonnement ionisant.....................................................................................................15
7. Rayonnements ionisants (rayons x, rayons gamma) : points importants .......................................................16
8. Renseignements généraux sur les doses de rayonnement et l’équipement..................................................17
9. Mesures de radioprotection mises en place par le service de radiologie........................................................17
10. Approche factuelle de demande d’examens radiologiques....................................................................................18
11. Annexe 1 : études de cas en radiologie factuelle ........................................................................................................19
12. Annexe 2 : test sur les principaux concepts..................................................................................................................22
Références ............................................................................................................................................................................................24
2
PRÉFACE 
Le présent guide d’introduction vise à fournir des renseignements 
concis et ciblés aux étudiants sur l’utilisation des rayonnements 
à visée diagnostique et la radioprotection, en mettant l’accent 
sur les modalités d’utilisation des rayons X. L’interprétation des 
images radiologiques est enseignée dans les facultés de médecine 
du monde entier, mais notre expérience collective révèle 
que bien peu de notions sont transmises sur les principes 
scientifiques qui sous-tendent la radiographie et les risques 
associés à l’exposition à certains types de rayonnement. Ce guide 
offre un bref survol des rayonnements ionisants, des doses 
associées aux divers examens radiologiques, des précautions 
à prendre chez les patientes enceintes et des techniques de 
radioprotection de base pour les médecins, les étudiants et les 
résidents. Nous espérons que cet ouvrage permettra de combler 
certaines lacunes et, à terme, d’améliorer la prise de décisions et 
la sécurité des patients.
OBJECTIFS
• Comprendre la production des rayons X et les 
diverses sources de rayonnements ionisants.
• Connaître les effets biologiques 
des rayonnements ionisants.
• Savoir comment se protéger lorsqu’on travaille à 
proximité de sources de rayonnements ionisants.
• Connaître la conduite à tenir chez les patientes enceintes 
nécessitant un examen d’imagerie médicale.
• Connaître la conduite à tenir chez les patientes ayant subi 
une radiographie sans savoir qu’elles étaient enceintes.
• Reconnaître les questions cliniques et scientifiques 
qui demeurent sans réponse dans le domaine 
de l’imagerie médicale.
• Savoir communiquer avec les patients et leur famille à 
propos des risques et des avantages de l’imagerie médicale.
INTRODUCTION
3
Les humains sont constamment exposés à des sources de 
rayonnement naturelles comme les rayons du soleil et les 
rayonnements cosmiques. Certains des aliments que nous 
consommons contiennent également des isotopes radioactifs 
d’origine naturelle, comme ceux du potassium et du carbone. 
On peut aussi être exposé aux rayonnements dans notre milieu 
de vie, notamment par l’inhalation de radon. Enfin, les sources 
de rayonnement artificielles comme l’équipement médical 
s’ajoutent aux sources naturelles pour former notre 
dose totale de rayonnement.
Les rayonnements auxquels nous sommes exposés peuvent 
être ionisants ou non ionisants. Les premiers possèdent assez 
d’énergie pour éjecter un électron de l’atome avec lequel ils 
entrent en interaction; les seconds, non. Un rayonnement 
ionisant se définit comme tout type de particule subatomique 
ou de photon de haute énergie qui cause la formation d’ions 
(atomes ou molécules chargés) lorsqu’il interagit avec la 
matière. Ces ions peuvent causer des dommages biologiques 
aux cellules. Les rayons cosmiques, les neutrons, les particules 
alpha, les rayons X, certains rayons ultraviolets et les rayons 
gamma sont tous des rayonnements ionisants. Ils contiennent 
assez d’énergie par photon pour éjecter des électrons des 
atomes avec lesquels ils entrent en interaction. La lumière 
visible, les ondes infrarouges, la plupart des rayons ultraviolets 
et les ondes de radiofréquence, cependant, ne sont pas ionisants.
Diverses modalités d’imagerie permettent de visualiser l’organisme. 
La plupart nécessitent le recours aux rayonnements pour obtenir 
une image claire de la région d’intérêt. Les rayons X, les rayons 
gamma et les ondes de radiofréquence sont des formes de 
rayonnement électromagnétique utilisées fréquemment dans 
les services d’imagerie. Avec d’autres types de rayonnement 
(comme les rayons cosmiques, les rayons ultraviolets, la 
lumière visible et les rayons infrarouges), ils constituent ce 
qu’on appelle le spectre électromagnétique. Chacun de ces 
types de rayonnement électromagnétique dégage une certaine 
quantité d’énergie. Plus la fréquence de l’onde est élevée, plus 
elle dégage d’énergie. Ainsi, les rayons infrarouges, les ondes 
de radiofréquence et la lumière visible possèdent moins 
d’énergie que les rayons X, les rayons gamma et les rayons 
cosmiques. Le tableau 1 donne des exemples de sources 
de rayonnement ionisant et non ionisant.
1. À PROPOS DES RAYONNEMENTS
Type Exemple d’utilisation
Rayonnement non ionisant
Ondes radio Station de radio
Micro-ondes Four à micro-ondes
Rayons infrarouges Télécommande
Lumière visible Ampoule électrique
Rayons ultraviolets Lampe bactéricide
Rayonnement ionisant
Rayons X Radiographie
Rayons gamma Tomographie par émission de positons
Tableau 1 — Sources de rayonnement ionisant et non ionisant
4
Les rayonnements ionisants et non ionisants sont tous deux utilisés 
dans les services d’imagerie diagnostique. Les techniques 
d’imagerie fondées sur les rayons X (comme la radiographie avec 
film, la radiographie numérique, la tomodensitométrie [TDM], 
la mammographie et la radioscopie) emploient toutes des 
rayonnements ionisants. Les techniques de médecine nucléaire 
(tomographie par émission de positons [TEP] et tomographie 
par émission de photon unique [TEPU]) reposent également sur 
un rayonnement ionisant, de rayons gamma. L’imagerie par 
résonance magnétique (IRM) est fondée sur un rayonnement 
non ionisant, les ondes de radiofréquence. En échographie, ce 
sont des ondes de pression (ondes mécaniques) qui servent 
à visualiser l’organisme. Veuillez prendre note toutefois que 
cette dernière technique n’est mentionnée que dans le but 
d’énumérer les modalités les plus souvent utilisées dans un 
service d’imagerie : les ondes sonores ne constituent pas un 
rayonnement électromagnétique. 
Dans le cas des techniques d’imagerie autres que l’échographie, 
l’IRM et les techniques de médecine nucléaire, une source externe 
génère des photons sous forme de rayons X. Lorsqu’ils pénètrent 
le corps, ces rayons sont absorbés ou diffusés (changement de 
trajectoire par rapport au faisceau incident) selon les éléments 
qu’ils rencontrent. Le faisceau qui émerge du corps du patient 
est donc atténué, ou moins intense, ayant perdu des photons par 
diffusion ou absorption lors du passage à travers la région visée. 
C’est lorsque ce faisceau atténué atteint un détecteur que 
l’image est générée. 
En médecine nucléaire, la source radioactive est interne 
plutôt qu’externe. On administre un radionucléide au patient, 
habituellement par injection ou inhalation. Ce radionucléide (la 
source) est d’abord lié à une molécule qui sera métabolisée par 
le système corporel ou le tissu pathologique à examiner (la cible). 
Le radionucléide, instable, subit une décroissance radioactive 
constante au cours de laquelle il émet des rayons gamma 
(rayons γ). Avec la concentration du radionucléide dans la 
région cible, le rayonnement gamma s’intensifie. Un détecteur 
externe mesure alors ce rayonnement, qui sert à produire les 
images cliniques.
Les rayons X et gamma se distinguent par leur origine dans le 
noyau atomique. Les premiers proviennent de l’extérieur du 
noyau, tandis que les seconds sont générés à l’intérieur du noyau 
d’un atome radioactif. Dans un système d’imagerie clinique, le 
faisceau de rayons X est produit par un tube à rayons X (figure 1a). 
À l’intérieur du tube, un faisceau d’électrons est généré en 
soumettant le filament à une émission thermo-ionique 
(chauffage du filament). La différence de potentiel du tube 
entraîne une accélération des électrons du faisceau vers l’anode 
(habituellement faite de tungstène, de molybdène ou de rhodium). 
Lorsque les électrons atteignent l’anode, leur énergie cinétique 
(produite par leur accélération résultant de la différence de 
potentiel du tube, ou kVp) est convertie en chaleur et en photons 
de rayonnement X (1) (figure 1b). Le spectre de rayons X continu 
produit par un faisceau d’électrons porte le nom de rayonnement 
de freinage (ou bremsstrahlung) (figure 2). Si la tension dans le 
tube est suffisante, les électrons incidents peuvent éjecter des 
électrons de l’atome cible. Les électrons des couches supérieures 
remplissent alors le vide créé, ce qui entraîne l’émission des 
rayons X caractéristiques (figures 3a et 3b). 
2. LES RAYONNEMENTS EN IMAGERIE MÉDICALE
Figure 1a — Diagramme d’un tube à rayons X. L’enveloppe de verre 
qui scelle l’intérieur du tube produit un vide poussé. Une haute tension est 
appliquée entre la cathode et l’anode (habituellement faite de tungstène).
Figure 1b — Émission continue de rayons X à partir d’un tube 
à rayons X. Le chauffage du filament libère des électrons qui font 
ensuite l’objet d’une accélération vers l’anode. L’arrêt abrupt 
des électrons produit les rayons X.
5
Les rayons gamma prennent naissance dans le noyau de l’atome 
radioactif, qui est instable et doit subir une transformation 
radioactive pour atteindre un état stable. Cette transformation 
peut prendre la forme d’une désintégration bêta-, bêta+ ou alpha, 
ou encore d’une capture électronique. La description complète 
de ces transformations dépasse la portée du présent guide 
d’introduction : les lecteurs qui souhaitent en savoir davantage 
sont invités à consulter un manuel de médecine nucléaire (2).
Quand les rayons gamma sont utilisés en imagerie, le rayonnement 
se poursuit après l’examen. En effet, puisque ce type de rayons 
est produit par une transformation radioactive, la source émet 
un rayonnement de façon constante. L’intensité du rayonnement 
émis dépend de la demi-vie du nucléide. Par conséquent, le patient 
demeure radioactif jusqu’à ce que la source soit complètement 
éliminée de l’organisme (par les selles, l’urine et la transpiration) 
ou qu’elle se soit suffisamment désintégrée pour atteindre 
le niveau de rayonnement naturel, après un laps de temps 
correspondant. En revanche, un patient exposé aux rayons X 
n’est pas radioactif après l’examen, puisque le rayonnement 
provient d’un tube à rayons X.
En radiographie diagnostique, les images sont formées par 
l’interaction entre le faisceau de rayons X, le patient et le 
détecteur. Lorsque le faisceau de rayons X passe à travers 
le corps du patient, les photons interagissent avec les tissus 
corporels. Le degré d’absorption dépend de la densité de la 
matière qui se trouve sur la trajectoire du faisceau. Les objets 
denses, comme les os ou le métal, absorbent très bien les 
photons, tandis que les objets moins denses, comme les tissus 
adipeux et l’eau, les absorbent moins. En fonction des différents 
degrés d’absorption des photons par différentes matières, 
le faisceau qui ressort de l’organisme, ou faisceau transmis, 
possède une intensité variable. La variation de l’intensité est 
ensuite mesurée à l’aide d’un détecteur, ce qui renseigne sur 
les différentes densités qu’a rencontrées le faisceau. 
En radiographie, le faisceau transmis est visualisé à l’aide d’un 
détecteur avec film ou d’un détecteur numérique. Sur un cliché 
simple, les zones d’intensité élevée (faible absorption par la 
matière) du faisceau transmis paraissent en noir, tandis que 
les zones de faible intensité (forte absorption par la matière) 
paraissent moins sombres. Dans les zones où aucun photon 
ne ressort, le film demeure blanc.
Puisque l’organisme est constitué de tissus de densité variable, 
les clichés radiographiques montrent une gamme de gris, où le 
noir correspond aux substances à faible coefficient d’atténuation 
(comme l’air) et le blanc, aux tissus à fort coefficient ’atténuation 
(comme l’os). 
Une radiographie simple peut être réalisée selon différentes 
orientations pour visualiser différents aspects de l’anatomie 
du patient. Les orientations les plus courantes sont l’incidence 
postéro-antérieure (PA, de l’arrière vers l’avant), antéropostérieure 
(AP, de l’avant vers l’arrière) et latérale (de profil). Des radiographies 
numériques peuvent également être produites au lieu de clichés 
avec film. La formation d’images au moyen de détecteurs numériques 
dépasse la portée du présent guide d’introduction : les lecteurs 
qui souhaitent explorer ce sujet sont invités à consulter le 
manuel en référence (1). La différence de potentiel des tubes 
habituels se situe entre 50 et 150 kVp.
Figure 2 — Production de rayonnement de freinage (ou bremsstrahlung). 
Lorsque le faisceau d’électrons incident passe près d’un noyau, il subit une 
forte déviation qui entraîne une perte d’énergie et l’émission de photons. 
Figure 3a — Lorsque le faisceau d’électrons incident possède suffisamment 
d’énergie, il peut éjecter des électrons de la cible (flèche verte).
Figure 3b — Le vide produit est ensuite rempli par les électrons 
des couches supérieures (flèche orange), provoquant l’émission 
de rayons X caractéristiques. 
6
La mammographie sert à déceler toute calcification (caractéristique 
de certains types de cancer du sein) ainsi que toute zone hypodense 
ou hyperdense qu’on remarque dans d’autres types de cancer 
(1, 4). Cet examen sert au dépistage comme au diagnostic. 
La visualisation du sein et la détection des anomalies par 
la mammographie s’effectuent à l’aide des rayons X, mais il 
existe des différences fondamentales entre les systèmes de 
mammographie et de radiographie diagnostique. En raison des 
caractéristiques du tissu mammaire et de la pathologie d’intérêt, 
la différence de potentiel des tubes à rayons X des systèmes 
mammographiques est plus faible qu’en radiographie 
diagnostique (de 15 à 35 kVp contre 50 à 150 kVp). De plus, 
deux plaques de compression sont utilisées pour diminuer 
l’épaisseur du sein et minimiser les mouvements, ce qui réduit la 
dispersion et donne des images d’une qualité globale accrue. 
La radioscopie est un examen en temps réel où une série de 
radiographies à faible dose de rayons X sont obtenues en un certain 
laps de temps. Elle est utile pour examiner le tractus gastro intestinal, les voies urinaires et le système musculosquelettique. 
L’angiographie est un examen radioscopique spécialisé où l’on 
utilise un produit de contraste pour mettre les vaisseaux du 
patient en évidence. Le produit radio-opaque (à haute densité) 
est injecté dans les vaisseaux sanguins du patient. Les vaisseaux 
qui contiennent le produit de contraste paraissent plus sombres 
sur l’image, tandis que ceux qui n’en contiennent pas paraissent 
plus clairs. Des techniques avancées comme l’angiographie numérique 
avec soustraction et les techniques de guidage cartographique 
(roadmapping) peuvent servir à améliorer la visualisation des 
vaisseaux et à guider les interventions percutanées.
La tomodensitométrie (TDM), en termes simples, repose sur 
des milliers de radiographies du patient, prises sous divers 
angles. Dans les systèmes de TDM les plus courants, un tube à 
rayons X et un détecteur tournent simultanément autour d’une 
partie du corps du patient tout en prenant des clichés. Lors du 
traitement de l’image, tous les plans d’acquisition sont compilés 
afin de reconstruire la coupe à visualiser. Ce processus est 
répété pour différentes zones de l’organisme, ce qui donne une 
pile de coupes axiales en 2D du corps du patient. Des techniques 
avancées d’acquisition de données et de traitement informatique 
peuvent servir à produire un éventail d’images, notamment des 
perspectives 3D. Les appareils de TDM d’aujourd’hui possèdent 
plus d’une série de détecteurs (tomodensitomètres multibarrettes). 
Ils peuvent donc réaliser plus d’une coupe à la fois. De nombreux 
services d’imagerie disposent de tomodensitomètres à 16 ou 64 
coupes, et certains établissements possèdent même des appareils 
à 320 coupes (3). En plus de cette technique en simultané, 
la TDM hélicoïdale permet un déplacement constant de la 
table d’examen au cours de l’acquisition d’images. L’imagerie 
multicoupe conjuguée au balayage hélicoïdal permet de réduire 
le temps d’examen.
En tomographie par émission de positons (TEP), la désintégration 
radioactive de la source administrée (comme le fluor 18) entraîne 
l’émission de positons (électrons possédant une charge positive). 
Lorsque ces particules entrent en collision avec les électrons de 
la matière, deux rayons gamma sont émis à un angle de 180 degrés. 
Ainsi, en TEP, les détecteurs en forme d’anneau sont placés tout 
autour du patient pour capter les photons émis. Une fois les paires 
de photons captées, une image montrant la répartition de la 
source radioactive peut être reconstruite par ordinateur. Puisque 
la source est interne, les différents tissus et les zones où le 
marqueur (c.-à-d., une substance pharmaceutique marquée à 
l’aide d’un radio-isotope) est plus ou moins capté paraissent 
comme des régions hyperdenses (zone chaude ou d’hypercaptation 
du marqueur) ou hypodenses (zone froide ou d’hypocaptation 
du marqueur) (1, 4).
La tomographie par émission de photon unique (TEPU) est 
une technique de médecine nucléaire qui ressemble à la TEP. 
Elle requiert également l’injection d’un isotope radioactif 
(comme le technétium 99m), habituellement fixé à une 
substance pharmaceutique. Toutefois, contrairement à la 
TEP, le radio-isotope utilisé pour la TEPU n’émet qu’un seul 
rayon gamma lors de la désintégration. Des gamma-caméras 
captent les rayons gamma émis. La reconstruction de l’image 
résultante peut être réalisée par diverses techniques, comme 
la rétroprojection filtrée. La TEPU comporte de nombreuses 
applications cliniques, notamment l’imagerie de la circulation 
sanguine cérébrale et du myocarde. 
7
3.1 ACTION DES RAYONNEMENTS 
IONISANTS 
Comme mentionné précédemment, les rayons gamma (utilisés 
en médecine nucléaire) et les rayons X (utilisés en TDM, 
radiographie, radioscopie et mammographie) constituent tous 
deux des rayonnements ionisants (voir la section 1). Lorsque 
ce type de rayonnement entre en interaction avec la matière, 
son énergie y est complètement ou partiellement transférée, 
ce qui entraîne des phénomènes d’excitation, d’ionisation et de 
chauffage de la zone exposée. En termes plus précis, l’action du 
rayonnement entraîne l’éjection d’un électron de l’atome cible. 
Si cet électron interagit ensuite avec des cibles critiques de la 
cellule, comme l’ADN, et produit une ionisation, on dit du 
rayonnement qu’il a une action directe. Au contraire, on dit que 
l’action est indirecte si l’électron éjecté interagit avec d’autres 
molécules de la cellule (comme l’eau, H2
O), produisant des radicaux 
libres (OH) qui, eux, entrent en interaction avec la cible critique. 
La figure 4 illustre les deux types d’action du rayonnement.
Qu’elle soit directe ou indirecte (figure 4), l’action du rayonnement 
entraîne la diffusion d’électrons ou de radicaux libres qui 
peuvent entrer en interaction avec l’ADN de la cellule et altérer 
sa structure de diverses façons. Il peut en résulter la rupture de 
liaisons hydrogène et des ruptures simple ou double brin (1). 
Une fois ces modifications moléculaires engendrées, la cellule 
peut réagir en activant des mécanismes de réparation des 
dommages. Toutefois, si des erreurs sont introduites au cours 
de la réparation de l’ADN, la cellule risque d’être détruite par 
apoptose (mort cellulaire programmée) ou par élimination 
mitotique (mort de la cellule au cours du cycle de division 
suivant). Si des erreurs sont introduites, mais que la cellule 
survit, il en résulte une mutation cellulaire.
Dans le cas de la description d’un organe, si les cellules sont réparées 
sans erreurs après l’exposition au rayonnement, aucun effet ne sera 
observé. L’effet du rayonnement ne sera pas non plus observable 
si les cellules instables sont éliminées, dans la mesure où un petit 
nombre de cellules meurent. Dans le cas d’une forte dose de 
rayonnement ou de la destruction de nombreuses cellules, l’organe 
risque de perdre une partie de ses fonctions. De telles doses ne 
sont toutefois pas habituelles en imagerie médicale. Enfin, la 
survie des cellules ayant subi une mutation peut conduire à la 
formation de cancers, si la mutation touche des cellules somatiques, 
ou à des effets héréditaires, si elle touche des cellules germinales (5). 
La réponse d’un organe au rayonnement et sa capacité de 
réparation dépendent de nombreux facteurs, notamment la dose 
reçue, le débit de dose, la présence de certaines molécules après 
l’exposition au rayonnement, le type de rayonnement utilisé, 
l’âge de la personne exposée et l’emplacement des zones 
endommagées des molécules d’ADN.
3.2 ORGANISMES DE RÉGLEMENTATION 
ET EFFETS DES RAYONNEMENTS
De nombreux comités consultatifs ont été mis sur pied pour 
examiner les conclusions scientifiques actuelles et les rapports 
publiés afin d’évaluer les effets des rayonnements ionisants. 
Citons à ce titre la Commission internationale de protection 
radiologique (CIPR), le National Council on Radiation Protection 
and Measurements (NCRP) et le Committee on the Biological 
Effects of Ionizing Radiation (BEIR). Les recommandations de la 
CIPR constituent les fondements des pratiques de radioprotection 
au Canada et dans la plupart des pays (6).
La CIPR classe les effets biologiques des rayonnements ionisants 
en deux catégories : déterministes et stochastiques (7). Les effets 
déterministes se produisent lorsque la dose dépasse un certain 
seuil, et leur gravité augmente avec la dose. Les cataractes et 
l’érythème (rougeurs cutanées) sont des exemples d’effets 
déterministes. Les effets stochastiques sont ceux dont la probabilité 
augmente avec la dose. Les cancers causés par les rayonnements 
et les effets génétiques sont des effets stochastiques. Les comités 
consultatifs s’entendent actuellement sur le fait que les effets 
stochastiques suivent une courbe linéaire sans seuil (7, 8), ce qui 
signifie que toute dose de rayonnement, même minime, comporte 
3. RAYONNEMENTS IONISANTS : CONCEPTS FONDAMENTAUX
Figure 4 — Action des rayonnements ionisants. Lorsque le rayonnement 
provoque l’éjection d’un électron (en gris dans la figure), il arrive que 
ce dernier interagisse avec des molécules d’eau pour produire des 
radicaux libres (partie supérieure de la figure). Ces radicaux peuvent 
ensuite frapper la cible critique. On qualifie ce phénomène d’action 
indirecte du rayonnement. L’action directe (partie inférieure de la 
figure) se produit lorsque le rayonnement éjecte un électron qui 
frappe la cible critique, causant des dommages biologiques.
8
un certain risque. Il est important de noter que l’utilisation d’un 
modèle linéaire sans seuil pour estimer le risque de cancer 
repose sur une extrapolation des risques liés à l’exposition à des 
doses et à des débits de doses élevés, pour lesquels les données 
de référence proviennent des populations des régions touchées 
par les bombes atomiques. Les débats se poursuivent quant à 
l’effet réel des rayonnements ionisants à faible dose comme ceux 
utilisés dans le cadre des examens d’imagerie. Certains chercheurs 
croient à l’existence de mécanismes adaptatifs de réparation, 
fondée sur des études radiobiologiques. En raison du peu de 
connaissances scientifiques entourant l’exposition à de faibles 
doses, la plupart des organismes préconisent le principe ALARA 
(« as low as reasonably achievable », ou viser les doses les plus 
faibles que l’on peut raisonnablement atteindre). Ainsi, puisque 
nous ne connaissons pas l’étendue des dommages pouvant être 
causés par une irradiation à faible dose, il faut atténuer les 
risques pour les générations futures en utilisant les doses les 
plus faibles possible. Le lecteur qui souhaite en savoir davantage 
sur les effets de faibles doses de rayonnements ionisants est 
invité à consulter les documents en référence (8, 9).
Quand un patient subit un examen d’imagerie mettant en jeu 
des rayonnements ionisants, les effets stochastiques sont ceux 
qui sont les plus préoccupants pour la santé. En fonction d’un 
modèle linéaire sans seuil, toute intervention où l’on administre 
une dose de rayonnement au patient augmente le risque qu’il 
subisse de tels effets. Les effets déterministes, en revanche, sont 
observés lorsque de fortes doses sont reçues, ce qui n’est pas le 
cas de la majorité des examens d’imagerie. La CIPR a établi les 
limites de dose recommandées pour les travailleurs exposés aux 
rayonnements et pour la population générale (voir le tableau 4 
à la section 4). Aucune limite n’a été établie pour l’exposition des 
patients dans un cadre médical. Il revient au médecin de décider 
si les avantages de l’examen l’emportent sur les risques liés aux 
rayonnements et à la prise en charge prudente sans information 
diagnostique. La CIPR préconise toutefois l’optimisation des 
mesures de radioprotection pour les interventions reposant 
sur les rayonnements ionisants (10).
3.3 RAYONNEMENTS IONISANTS : 
QUANTIFICATION, EXPOSITION 
ET RISQUE
Un certain nombre de mesures est utilisé pour calculer la dose 
de rayonnement. Le terme exposition correspond aux ions 
(particules chargées) produits par un champ de rayonnement 
dans un volume d’air donné. Deux matériaux différents exposés 
au même champ de rayonnement n’absorbent toutefois pas la 
même quantité d’énergie. Ainsi, bien que le niveau d’exposition 
rende compte de l’ionisation présente, il n’explique pas comment 
l’organisme répond à cette énergie. Le terme dose absorbée, 
mesurée en gray (Gy, où 1 Gy = 1 joule/kg), renvoie à la quantité 
d’énergie absorbée par unité de masse. Or, la même partie du 
corps exposée à deux types de rayonnements ionisants ne subit 
pas les mêmes dommages biologiques, qui sont plus ou moins 
graves selon le type de rayonnement. Pour rendre compte des 
effets biologiques des rayonnements, on utilise donc le terme 
dose équivalente. Mesurée en sievert (Sv), il s’agit de la mesure 
la plus précise pour comparer les effets radiobiologiques de 
différentes interventions médicales (11). On retrouve également 
des unités et des termes qui n’appartiennent pas au SI (système 
international d’unités), comme le rad (« radiation absorbed dose », 
dose de rayonnement absorbée), le roentgen et le rem, mais leur 
utilisation est aujourd’hui déconseillée (11). Les lecteurs qui 
doivent employer ces unités trouveront facilement les définitions 
et les facteurs de conversion correspondants dans d’anciennes 
éditions de manuels de physique médicale. 
Afin de mettre en perspective les doses reçues lors d’examens 
médicaux, il est utile d’établir la comparaison avec le 
rayonnement naturel de fond. Dans la vie de tous les jours, 
nous sommes exposés à un certain rayonnement de fond 
provenant de sources naturelles comme les rayons cosmiques, 
le gaz atmosphérique (radon) et la désintégration des radioisotopes 
du carbone et du potassium présents dans le corps (voir la 
section 1). La dose efficace moyenne de rayonnement naturel 
Source de rayonnement Contribution à la dose efficace totale (%)
Rayonnement naturel ambiant 50
Interventions médicales 48
Produits de consommation 2
Autres (centrales nucléaires / retombées radioactives) < 0,1
Tableau 2 — Contribution des sources courantes de rayonnement. Données tirées de (13)
9
de fond mesurée en un an au Canada est de 1,77 mSv (12). La 
dose annuelle de rayonnement naturel de fond mesurée dans le 
monde varie entre 1 et 10 mSv, avec une moyenne de 2,4 mSv 
(8). Outre la dose naturelle, la population est exposée à d’autres 
sources de rayonnement. Le tableau 2 présente les sources 
d’exposition courantes. Les interventions radiologiques entraînent 
une certaine dose de rayonnement, qui dépend du type d’examen 
et de la région visée. Le tableau 3 indique la dose de rayonnement 
reçue lors de divers examens d’imagerie ainsi que la période 
d’exposition équivalente au rayonnement naturel de fond.
La CIPR a établi les limites de dose recommandées pour les 
travailleurs exposés aux rayonnements et pour la population 
générale (voir le tableau 4 à la section 4). Aucune limite n’est 
établie en ce qui a trait à la dose reçue par le patient. Il revient 
au médecin de juger si les avantages d’une intervention mettant 
en jeu les rayonnements ionisants l’emportent sur les risques 
encourus. On doit en outre respecter le principe ALARA et 
prendre les mesures appropriées pour éviter toute 
exposition inutile. 
Examen Dose efficace de 
rayonnement (mSv)
Exposition équivalente au 
rayonnement naturel
Ostéodensitométrie 0,01 1 jour
Radiographie pulmonaire 0,1 10 jours
Galactographie 0,7 3 mois
Mammographie 0,7 3 mois
Pyélographie intraveineuse 1,6 6 mois
Radiographie du tractus 
gastro-intestinal supérieur
2 8 mois
Radiographie du tractus 
gastro-intestinal inférieur
4 16 mois
Myélographie 4 16 mois
TDM
Sinus 0,6 2 mois
Cardiaque, score calcique 2 8 mois
Tête 2 8 mois
Colonographie 5 20 mois
Thorax 8 3 ans
Abdomen 10 3 ans
Corps entier 10 3 ans
Rachis 10 3 ans
Tableau 3 — Dose de rayonnement propre à diverses interventions, comparativement au rayonnement naturel Données tirées de (14, 15).
10
Aux fins de radioprotection, la CIPR a établi les limites de dose 
recommandées pour les travailleurs exposés aux rayonnements 
(personnes qui travaillent en présence de rayonnements d’origine 
artificielle) et pour la population en général. Ces limites sont 
présentées dans le tableau 4. Veuillez prendre note qu’elles 
n’incluent pas les doses reçues lors d’interventions médicales 
ou par le rayonnement naturel de fond. 
Puisqu’on présume actuellement que toute imagerie radiologique 
qui met en jeu les rayonnements ionisants présente un certain 
niveau de risque, la protection du patient et du personnel doit 
être assurée. Aucune limite précise n’a été établie à l’heure 
actuelle en ce qui a trait à l’exposition résultant de l’imagerie 
médicale. On doit donc évaluer les avantages de chaque exposition 
pour le patient comparativement aux risques perçus. Afin de 
maximiser les avantages pour le patient, on doit chercher à 
réduire par tous les moyens les risques liés à l’intervention. Il 
arrive toutefois que l’atténuation des risques d’un examen ne 
passe pas par la réduction de la dose de rayonnement reçue. Par 
exemple, il se peut qu’en tentant de réduire de la dose totale de 
rayonnement reçue par le patient, on diminue la qualité de 
l’image. Dans certains cas, une telle diminution représente un 
plus grand risque pour le patient (risque d’erreur de diagnostic) 
que le risque potentiel associé à la radioexposition. 
4. RAYONNEMENTS IONISANTS : PROTECTION
Type de limite Exposition professionnelle Population générale
Corps entier 20 mSv par année en moyenne 
sur une période de 5 ans
1 mSv par année
Dose annuelle dans :
le cristallin 150 mSv 15 mSv
la peau 500 mSv 50 mSv
les mains et les pieds 500 mSv -
Tableau 4 — Limites de dose recommandées par la CIPR pour les situations d’exposition planifiée (7)
11
La réduction de l’exposition professionnelle repose sur trois 
critères de radioprotection : le temps, la distance et l’équipement 
de protection individuelle (ÉPI). Le premier critère renvoie au temps 
passé à proximité du rayonnement : réduire le temps passé dans 
une salle d’examen en présence de rayons X ou au côté de patients 
traités en médecine nucléaire réduira la dose reçue par les travailleurs. 
Le deuxième critère renvoie à la distance qui sépare le personnel 
du rayonnement. L’exposition diminue habituellement selon la 
loi de l’inverse des carrés, soit 1(distance)2. Par exemple, en 
augmentant la distance de la source de rayonnement de 1 à 3 mètres, 
on réduit l’exposition à 1/9e de la dose initiale. On effectue une 
telle séparation spatiale en désignant des aires « sécuritaires ». 
Le personnel médical ne devrait normalement pas être présent 
dans la salle d’examen, sauf si c’est absolument nécessaire. Dans 
de tels cas, les trois principes de la radioprotection doivent être 
respectés. En veillant à ce que seul le minimum de personnel soit 
présent pour chaque examen, on limite également l’erreur humaine 
et l’exposition (16). Les aires sécuritaires sont des salles d’où le 
personnel médical peut observer le déroulement de l’examen 
sans s’exposer à la source de rayonnement. Elles sont 
habituellement adjacentes à la salle d’examen, la cloison 
mitoyenne comportant une fenêtre d’observation. Là où des 
appareils radiologiques portatifs sont utilisés, comme au service 
d’urgence, aux soins intensifs ou en salle d’opération, la séparation 
spatiale peut également être réalisée à l’aide d’un blindage ou 
d’écrans portatifs. Seul le personnel essentiel à l’examen devrait 
se tenir à proximité. Le troisième critère renvoie à l’usage adéquat 
d’équipement de protection : tabliers, vestes et jupes plombés, 
protecteurs thyroïdiens, lunettes avec verres plombés, écrans 
de protection suspendus, écrans fixés sur les tables et écrans 
plombés mobiles. On conseille fortement aux membres du personnel 
d’utiliser de l’ÉPI pour réduire autant que possible leur exposition 
professionnelle. En plus des trois principes de sécurité, le blindage 
de la salle d’examen doit être examiné par un expert qualifié, 
comme un physicien médical, pour vérifier que le personnel et 
les autres personnes présents à proximité ou dans la cabine de 
contrôle sont suffisamment protégés des rayonnements.
Le dernier accessoire de radioprotection est le dosimètre, qui 
sert à mesurer le rayonnement absorbé par chacun des membres 
du personnel médical. En vertu des lois provinciales de sécurité 
du travail, l’usage du dosimètre est obligatoire dans toutes les 
provinces canadiennes pour les personnes considérées comme 
courant un risque élevé d’exposition professionnelle. Les 
dosimètres peuvent être portés de deux façons. Premièrement, 
on peut les porter sous les vêtements de protection afin de 
mesurer le rayonnement qui pénètre le corps malgré l’ÉPI, 
vérifiant ainsi que celui-ci est utilisé de façon optimale. Un 
deuxième dosimètre peut également être porté par-dessus le 
tablier plombé, habituellement autour du cou, afin de mesurer 
le rayonnement absorbé par le visage, le cou, le crâne et les yeux. 
Les dosimètres permettent de mesurer les doses absorbées par 
chacun des membres du personnel médical pour vérifier qu’elles 
demeurent sécuritaires et que les limites de dose mensuelles, 
trimestrielles et annuelles ne sont pas dépassées (18).
12
Le grand public et les spécialistes du domaine médical 
s’interrogent à l’heure actuelle sur les risques que présentent 
les examens radiologiques pour les femmes enceintes et les 
enfants à naître. On relève à ce titre un grand nombre de 
publications contradictoires qui appuient ou déconseillent tour 
à tour le recours à l’imagerie pendant la grossesse (19). L’effet 
des rayonnements in utero dépend de la dose reçue et du stade 
de la grossesse auquel l’exposition a lieu. La grossesse peut 
être divisée en trois stades : la période de préimplantation, 
l’organogénèse et le développement fœtal. Les radiolésions lors 
du premier stade auraient un effet de type « tout ou rien » : soit 
la mort de l’embryon, soit la poursuite du développement de 
manière normale. On estime que le seuil s’établit à au moins 
60 mGy et qu’il varie fortement. Il importe de noter que le taux 
de base de fausse couche (avortement spontané) à ce stade 
de la grossesse se situe entre 30 et 50 % (1). Au stade de 
l’organogénèse, on observe la différenciation des cellules 
des diverses structures organiques, qui peut donner lieu à des 
malformations congénitales. Bien que peu courant compte tenu 
des doses administrées en imagerie diagnostique, le retard de 
croissance du fœtus est l’effet le plus couramment observé chez 
les femmes enceintes exposées durant la période située entre 
une et huit semaines de grossesse (20). Finalement, durant le 
stade de développement fœtal, les malformations du système 
nerveux sont le principal problème associé à la radioexposition. 
Ces anomalies, qui peuvent entraîner entre autres la microcéphalie, 
la déficience mentale et les crises épileptiques, peuvent survenir 
entre 8 et 15 semaines après l’implantation, soit la période où 
s’effectue la majeure partie du développement neuronal du 
fœtus (20). Un risque de déficience mentale existe également 
lors de l’exposition entre 16 et 25 semaines de gestation. Il 
semble cependant que les malformations causées par les 
rayonnements surviennent lorsque la dose dépasse un certain 
seuil. Le tableau 5 présente l’estimation des doses qui peuvent 
causer diverses malformations fœtales, ainsi que le stade de 
la grossesse où le risque est le plus élevé (21).
5. RAYONNEMENTS IONISANTS : PATIENTES ENCEINTES
Malformation Période où le risque est 
le plus élevé (semaines 
après la conception) 
Seuil estimé de dose de 
rayonnement (mGy)
Microcéphalie de 8 à 15 ≥ 20 000
Déficience mentale
de 8 à 15 60 – 310
de 16 à 25 250 – 280
Autres (malformations du squelette, des 
organes génitaux, des yeux)
de 3 à 11 ≥ 200
Diminution du QI de 8 à 15 100
Tableau 5 — Malformations causées par l’exposition du fœtus aux rayonnements durant divers stades de la grossesse. Données tirées de (21)
Aux fins de comparaison avec les valeurs du tableau 5, les doses que reçoit le fœtus lorsque la mère subit des examens 
diagnostiques sont présentées dans le tableau 6 (22). 
13
Examen Dose fœtale (mGy) 
Radiographie
Membre supérieur < 0,01
Membre inférieur < 0,01
Thorax (deux clichés) < 0,10
Cholécystographie 0,05 – 0,60
Bassin 0,40 – 2,38
Tractus gastro-intestinal supérieur (baryum) 0,48 – 3,60
Hanche et fémur 0,51 – 3,70
Abdomen (reins, uretères et vessie) 2,00 – 2,45
Colonne lombaire 3,46 – 6,20
Urographie (pyélographie intraveineuse) 3,58 – 13,98
Lavement baryté 7,00 – 39,86
Pyélographie rétrograde 8,00
TDM
Tête < 0,50
Thorax 1,00 – 4,50
Abdomen (10 coupes) 2,40 – 26,0
Abdomen et bassin 6,40
Bassin 7,30
Colonne lombaire 35,00
Autre
Scintigraphie de ventilation-perfusion 0,60 – 10,00
Tableau 6 — Doses de rayonnement estimées reçues par le fœtus lors d’examens d’imagerie diagnostique courants. Données tirées de (22)
14
Pour la plupart des examens radiologiques, la dose reçue par le fœtus 
en développement est inférieure à 50 mGy (tableau 6). Il 
importe de noter que les valeurs indiquées dans le tableau 6 sont 
approximatives et peuvent varier en fonction des paramètres de 
balayage et des particularités anatomiques des patientes. Dans 
la plupart des examens d’imagerie, le fœtus reçoit des doses plus 
faibles que la mère en raison de la protection qu’offre l’utérus (23). 
Pour toute radiographie effectuée chez une femme enceinte, le 
fœtus reçoit une certaine dose de rayonnement, par exposition 
directe ou indirecte. L’exposition directe survient lorsque le fœtus 
est dans le champ de visualisation, comme dans les examens du 
bassin et de l’abdomen. L’exposition indirecte résulte du transfert 
interne du rayonnement des tissus de la mère au fœtus. Les examens 
de la tête, du cou, des membres et du thorax présentent de très 
faibles risques d’exposition directe si les mesures de protection 
adéquates sont prises, mais ils constituent toujours un certain 
risque d’exposition indirecte. Le risque d’exposition indirecte 
est plus important lorsqu’un passage transplacentaire est 
possible, comme pour les examens exigeant l’administration 
d’iode ou de gallium radioactifs (20). 
La perception des risques de la radiographie au sein de la 
population et chez les médecins influence les tendances 
actuelles en matière d’utilisation de ce type d’examen chez 
les femmes enceintes. Dans une étude réalisée auprès de 98 
femmes, le risque tératogène perçu par celles ayant subi un 
examen radiodiagnostique était beaucoup plus élevé (25,5 %) 
que chez celles n’ayant pas subi de tel examen (15,7 %) (24). 
Ces chiffres reflètent la perception générale de l’imagerie 
radiologique comme étant néfaste pour le fœtus. Les études 
au sujet de la perception de la tératogénicité des examens 
radiologiques chez les médecins ont révélé que la plupart 
d’entre eux surestiment le risque de dommages et font donc 
preuve de prudence quant à l’utilisation des rayons X chez les 
patientes enceintes. Dans le cadre d’une étude canadienne, on 
a demandé à 287 obstétriciens et médecins de famille d’estimer 
le risque qu’encourt le fœtus lorsque la mère subit un examen 
radiographique ou par TDM de l’abdomen. Parmi les répondants, 
44 % des médecins de famille et 11 % des obstétriciens ont 
estimé le risque tératogène d’une radiographie de l’abdomen 
à plus de 5 % (25). En outre, 1 % des médecins de famille ont 
indiqué qu’ils recommanderaient l’avortement si la mère était 
exposée aux rayonnements lors d’une radiographie abdominale, 
tandis que 6 % d’entre eux recommanderaient l’avortement 
après un examen par TDM de l’abdomen (25). Ces exemples 
illustrent que même ceux qui prescrivent les examens se 
méprennent souvent sur le risque qu’ils présentent pour les 
femmes enceintes. Il se peut qu’un tel excès de prudence résulte 
d’une méconnaissance des doses de rayonnement découlant des 
différentes modalités d’imagerie (26) ou d’une surestimation 
de leur risque tératogène inhérent. 
Malgré la perception actuelle au sein de la population, la plupart 
des techniques de radiographie exposent le fœtus à de faibles 
doses de rayonnement, inférieures à 50 mGy, pour lesquelles 
aucun risque fœtal significatif n’a été observé. Comme pour 
tous les actes médicaux, les risques et les avantages de toute 
intervention diagnostique doivent être évalués au cas par cas. 
De plus, les doses reçues lors d’examens radiologiques doivent 
être mieux comprises afin de réduire l’anxiété chez les patientes 
enceintes et d’éviter les interruptions de grossesse inutiles.
Selon l’American Congress of Obstetricians and 
Gynecologists (ACOG), le risque pour le fœtus est minimal 
pour des doses inférieures à 50 mGy, et les doses supérieures 
à 100 mGy n’augmentent que de 1 % le risque de malformation, 
par rapport à l’incidence de base.
15
Afin d’éviter les risques associés aux rayonnements ionisants, 
qui varient en fonction de la dose reçue, d’autres modalités 
d’imagerie peuvent être utilisées. L’échographie et l’imagerie par 
résonance magnétique (IRM) n’exposent pas aux rayonnements 
ionisants et peuvent constituer les modalités de première 
intention dans de nombreuses situations.
6.1 ÉCHOGRAPHIE
Parfois nommée ultrasonographie ou sonographie, l’échographie 
consiste à utiliser un transducteur pour envoyer des ondes 
sonores à haute fréquence dans l’organisme afin de produire 
une image de la partie du corps à examiner. L’échographie 
comporte des applications dans de nombreuses branches de 
la médecine et peut servir dans le cadre d’interventions tant 
diagnostiques que thérapeutiques, comme les biopsies ou 
l’aspiration à l’aiguille. Voici quelques-unes des applications 
courantes de l’échographie (27) :
• Cardiologie – échocardiographie, qui exige le recours 
à une sonde transoesophagienne
• Gynécologie et obstétrique
• Urologie – techniques d’imagerie externes et internes 
chez l’homme et la femme; utilisation d’ultrasons ciblés 
pour détruire les calculs rénaux par lithotritie
• Imagerie du système musculosquelettique
• Exploration intravasculaire
L’échographie est considérée comme sécuritaire, aucun effet 
indésirable clinique ou biologique associé à l’exposition aux 
ultrasons n’ayant été signalé pour les millions d’examens 
réalisés à ce jour (28). Bien que l’échographie permette 
d’évaluer de nombreuses pathologies, elle n’est toutefois pas 
très efficace dans les régions recelant une grande quantité d’air, 
puisque les ondes ultrasonores ne se transmettent pas bien dans 
l’air. Il ne s’agit donc pas de la modalité idéale pour visualiser 
l’intestin ou l’estomac, les zones cachées par ces organes, ainsi 
que l’intérieur des os et des grandes articulations (27).
6.2 IMAGERIE PAR RÉSONANCE 
MAGNÉTIQUE
En imagerie par résonance magnétique (IRM), les propriétés 
magnétiques et de résonance de la matière sont exploitées pour 
générer une image de la région d’intérêt. Dans la plupart des 
applications cliniques, on utilise le noyau des atomes d’hydrogène 
(un seul proton) pour obtenir l’image, en raison de leur abondance 
dans l’organisme. D’autres noyaux, comme ceux des atomes de 
phosphore, de sodium et de carbone, peuvent également servir 
à mieux comprendre le métabolisme de certaines molécules 
(l’ATP, par exemple, peut être étudié au moyen des techniques 
d’imagerie du phosphore). Il importe toutefois de noter que 
l’imagerie des noyaux autres que l’hydrogène est surtout utilisée 
à des fins de recherche; les images cliniques sont presque 
toujours obtenues à partir des noyaux d’hydrogène. 
L’IRM est très utile pour évaluer un large éventail d’affections. 
Elle peut produire des images très détaillées des tissus mous 
sous des angles multiples, ce qui permet de visualiser les lésions 
focales et de détecter les anomalies qui seraient camouflées sur 
un plan unique (29). On peut également étudier la connectivité 
cérébrale à l’aide d’une technique appelée IRM fonctionnelle 
(IRMf). Lorsqu’une région du cerveau est active, le flux sanguin 
y est accentué. Toutefois, la quantité d’oxygène extraite est 
inférieure à la quantité amenée par le sang, ce qui entraîne une 
diminution de la quantité de désoxyhémoglobine présente dans 
la région, comparativement à l’état de repos. Le signal utilisé en 
IRMf est sensible au rapport oxyhémoglobine-désoxyhémoglobine. 
Le changement associé à l’activité cérébrale peut donc être 
visualisé sur certaines images de résonance magnétique et 
servir à comprendre quelles régions du cerveau sont associées 
à des tâches précises.
6.3 AUTRES OPTIONS
Outre les modalités d’imagerie diagnostique, il est également 
possible de visualiser la région d’intérêt à l’aide de techniques 
effractives. Selon la région, l’examen peut se faire par l’insertion 
d’un tube optique (comme les techniques de laparoscopie, 
d’endoscopie et d’arthroscopie) ou par une technique ouverte 
(30). Ces techniques ne font pas appel aux rayonnements 
ionisants, mais elles demandent une expertise chirurgicale 
et présentent les risques généralement associés à la chirurgie : 
lésion, infection, saignement, perforation des viscères et 
réaction à l’anesthésique (31). En outre, certaines régions 
anatomiques ne peuvent être visualisées de cette façon, comme 
les organes rétropéritonéaux et l’aspect postérieur du foie (31).
6. MODALITÉS D’IMAGERIE SANS RAYONNEMENT IONISANT 
16
• La manipulation des isotopes et l’optimisation de 
l’équipement de radiographie sont réglementées et ne 
peuvent être effectuées que par le personnel qualifié. 
• L’équipement de radioscopie est utilisé par des médecins 
non radiologistes dans les salles d’opération, les unités de 
soins intensifs, les laboratoires de cathétérisme cardiaque et 
les services d’urologie. Seuls les médecins ayant reçu une 
formation en la matière peuvent utiliser ce type d’équipement.
• Les personnes qui participent à l’exécution d’interventions guidées 
par radioscopie doivent suivre les règles de sécurité suivantes :
1. Porter de l’équipement de protection, notamment un 
tablier plombé couvrant le thorax, l’abdomen, le bassin 
et les fémurs, des lunettes de protection ainsi qu’un 
protecteur thyroïdien plombé.
2. Éviter de placer les mains et les bras dans 
la trajectoire du faisceau de rayons X.
3. Rester aussi loin que possible de la source 
des rayons X durant l’exposition.
4. Ne jamais exposer son dos non protégé 
à la source active de rayons X.
5. En cas de grossesse, éviter l’exposition.
6. Utiliser des écrans protecteurs contre les rayons X.
7. Les examens de TDM peuvent être observés en toute 
sécurité à partir de la console du technologue. Des 
précautions s’appliquent concernant les patients 
auxquels des isotopes ont été administrés par injection, 
inhalation ou voie orale. Elles doivent être respectées!
7. RAYONNEMENTS IONISANTS 
(RAYONS X, RAYONS GAMMA) : POINTS IMPORTANTS
17
• Plus on s’approche de la source de rayonnement, 
plus la dose reçue augmente.
• La dose de rayonnement diminue considérablement 
avec la distance.
• Les écrans de protection diminuent la dose 
de rayonnement de façon importante.
• Une diffusion du rayonnement peut survenir, particulièrement 
durant les examens des os.
• Le mode d’utilisation de l’équipement radiologique proprement 
dit dépasse la portée du présent guide d’introduction.
• Les étudiants peuvent également être exposés aux 
rayons X sur les étages, lors d’examens à l’aide d’appareils 
radiologiques mobiles. Dans de tels cas, il faut respecter 
les panneaux de mise en garde contre les rayonnements 
et demeurer loin de la source des rayons X et du patient 
qui subit l’examen.
• Durant leur stage en radiologie, il se peut que les 
étudiants participent à des interventions reposant sur 
les rayons X. Si ces interventions ont lieu dans les unités 
d’angiographie ou de radioscopie, les précautions décrites 
à la section 7 s’appliquent.
8. RENSEIGNEMENTS GÉNÉRAUX SUR LES DOSES 
DE RAYONNEMENT ET L’ÉQUIPEMENT
De nombreuses mesures de radioprotection sont en place 
dans les services de radiologie afin de protéger les patients 
et le personnel des services de soins de santé :
• Les murs et les portes des salles de radiologie (radiographie 
générale, radioscopie, angiographie et TDM) sont doublés de 
plomb. Une telle mesure n’est pas nécessaire pour les salles 
d’IRM et d’échographie. 
• Les portes des salles de radiologie sont fermées avant 
tout examen.
• Les fenêtres d’observation entre les salles de commande 
et d’examen sont faites de verre au plomb.
• Des écrans protecteurs faits de plomb ou de verre au plomb 
sont accessibles dans les salles d’imagerie afin de protéger 
le personnel qui doit demeurer dans la salle durant l’examen 
pour aider le patient.
• Les aires réservées à la radiologie sont clairement indiquées 
et leur accès est limité au personnel autorisé.
• Des tabliers plombés, des blouses de protection, des gants 
plombés et des protecteurs thyroïdiens sont facilement 
accessibles. L’intégrité de l’ÉPI doit être assurée par des 
tests d’assurance qualité conformes aux règlements de 
l’hôpital ou au Code de sécurité 35 de Santé Canada.
9. MESURES DE RADIOPROTECTION MISES EN 
PLACE PAR LE SERVICE DE RADIOLOGIE 
18
L’approche des soins de santé fondés sur des données probantes 
est une méthode dynamique qui consiste à prendre les décisions 
cliniques concernant la prise en charge d’un patient en fonction 
des données actuelles et exactes issues de la recherche. La prise 
de décision fondée sur des données probantes (32) consiste à 
faire appel aux meilleures données disponibles pour évaluer 
les options de traitement d’un patient. Les principes des soins 
de santé fondés sur des données probantes peuvent être appliqués 
à toutes les étapes du processus de prise de décision en milieu 
clinique, y compris en radiologie. En ce qui a trait à la radiologie 
fondée sur des données probantes, ou radiologie factuelle, 
l’évolution constante des connaissances médicales et de la 
technologie pose un défi aux radiologistes, qui doivent choisir 
des méthodes d’examen à la fois économiques et utiles d’un 
point de vue clinique.
Compte tenu du nombre et de la complexité des examens 
radiologiques réalisables à l’heure actuelle, il revient au radiologiste 
de se fonder sur les données probantes disponibles afin de 
déterminer quelle méthode est la plus sensée, la plus économique 
et la plus utile dans un cas particulier. En suivant les principes 
de la médecine factuelle, on peut explorer comment prioriser les 
diverses méthodes d’examen en fonction des données issues de 
la recherche. Règle générale, les doses de rayonnement doivent 
toujours demeurer les plus basses possible. Les examens ne 
devraient donc être demandés qu’après avoir tenu compte de 
tous les antécédents radiologiques du patient. Afin de simplifier et 
de classer les doses de rayonnement, les niveaux de rayonnement 
relatifs (Relative Radiation Levels) déterminés par l’American 
College of Radiologists (ACR) sont présentés dans le tableau 7 (33).
10. APPROCHE FACTUELLE DE DEMANDE 
D’EXAMENS RADIOLOGIQUES
Niveau de rayonnement relatif Échelle de doses efficaces estimées (mSv) 
Aucun 0
Minime < 0,1
Faible 0,1 – 1
Moyen 1 – 10
Élevé 10 – 100
Tableau 7 — Niveaux de rayonnement relatifs tirés des lignes directrices de l’ACR (33)
La radiologie factuelle peut être pratiquée dans le cadre de nombreux scénarios cliniques qui exigent tous d’obtenir 
les antécédents complets du patient et d’effectuer un examen physique pertinent. 
19
Étude de cas : Douleur au quadrant 
supérieur droit (QSD)
Une douleur aiguë au QSD est un signe clinique courant associé 
à la cholécystite aiguë ou à la cholédocholithiase. Les méthodes 
d’imagerie le plus souvent accessible dans de tels cas sont 
l’échographie en temps réel, la choléscintigraphie (médecine 
nucléaire), la radiographie simple et la tomodensitométrie. 
Nous allons à présent examiner un scénario clinique et discuter 
de l’approche factuelle à adopter afin de choisir la modalité 
d’imagerie la plus logique dans la situation.
Scénario de radiologie factuelle I
Problème : Femme de 42 ans présentant une 
douleur aiguë au quadrant supérieur droit. 
Dans ce scénario, la probabilité d’une maladie de la vésicule 
biliaire est très élevée. Avec quels outils radiologiques peut-on 
visualiser la vésicule biliaire? L’analyse des options d’imagerie 
révèle que plusieurs types d’examens sont possibles : l’échographie 
en temps réel, la scintigraphie hépatobiliaire (médecine nucléaire), 
la radiographie simple et la tomodensitométrie (TDM) (33). En 
partant de l’hypothèse que la dose de rayonnement minimale est 
la meilleure conduite à tenir, nous concluons que l’échographie 
en temps réel est la première approche à adopter pour examiner 
la région de la vésicule biliaire chez cette patiente. En effet, en 
échographie, la patiente n’est exposée à aucun rayonnement 
ionisant. De plus, selon les critères de pertinence de l’ACR, 
l’échographie en temps réel est la méthode de première ligne 
standard pour l’évaluation des maladies vésiculaires. 
L’échographie en temps réel utilisée pour diagnostiquer la 
cholédocholithiase est une technique indolore et pratiquement 
sans risque (34). Bien qu’un jeûne de six heures soit nécessaire 
avant l’examen, l’examen lui-même ne prend que 15 minutes à 
réaliser. Dans jusqu’à 95 % des cas, les résultats sont concluants 
et aucun autre examen n’est nécessaire. Les deux principaux 
critères de diagnostic de calculs biliaires sont (1) la non-visualisation 
de la vésicule biliaire et (2) la présence de zones hyperéchogènes 
pouvant être accompagnées d’un cône d’ombre. Ces critères 
correspondent à une vésicule biliaire atteinte de fibrose et remplie 
de petits calculs. L’échographie en temps réel présente ici une 
sensibilité de 89 % et une spécificité de 97 % (34). L’approche de 
base pour établir un diagnostic de cholécystite aiguë résultant d’une 
obstruction par calculs biliaires est illustrée à la figure 5 (27).
L’imagerie par résonance magnétique n’est pas indiquée dans ce 
cas en raison de son coût relativement élevé. D’autres scénarios 
mettant en cause une douleur au quadrant supérieur droit 
peuvent toutefois exiger le recours à des examens radiologiques 
supplémentaires. En voici quelques exemples :
• Recherche des complications d’une cholécystopathie
• Formation d’abcès
• Perforation 
• Iléus biliaire
• Impossibilité de visualiser la vésicule biliaire pour 
l’une des raisons suivantes :
• Présence de gaz au-dessus des zones à visualiser
• Foie situé trop haut
• Calcification de la paroi de la vésicule biliaire.
Dans les cas ci-dessus, l’option suivante serait l’examen en 
médecine nucléaire ou la TDM. Bien que ces deux techniques 
exposent la patiente à des rayonnements, elles permettent 
d’outrepasser les limites de l’échographie et de visualiser 
plus clairement la zone critique. 
11. ANNEXE 1 : ÉTUDES DE CAS EN 
RADIOLOGIE FACTUELLE
20
Scénario de radiologie factuelle II
Problème : Homme de 55 ans souffrant depuis une semaine 
d’une toux productive, de faiblesse et de fièvre.
Dans ce scénario, la probabilité d’une pneumonie extrahospitalière 
est très élevée. L’analyse des examens radiologiques disponibles 
révèle encore une fois différents types d’examens possibles : la 
radiographie pulmonaire simple ou la TDM. L’échographie n’est 
pas indiquée puisqu’elle ne permet pas de visualiser les tissus 
pulmonaires autres que la plèvre. Comme l’indique la figure 6, 
la radiographie pulmonaire simple est la première approche à 
adopter pour examiner la région thoracique chez ce patient. 
L’examen n’expose le patient qu’à une dose de 0,7 mSv, classée 
comme une dose faible. De plus, selon les critères de pertinence 
de l’ACR, la radiographie pulmonaire simple est l’examen à 
privilégier lorsqu’on observe un tel tableau clinique chez 
un patient de plus de 40 ans (33).
La radiographie pulmonaire simple est un examen économique 
largement utilisé qui permet d’évaluer la consolidation du tissu 
pulmonaire. Elle permet également de découvrir des problèmes 
connexes comme l’épanchement pleural, ou encore des pathologies 
sous-jacentes comme le cancer bronchique ou la bronchectasie. 
La TDM, quant à elle, peut servir à évaluer les complications 
comme l’empyème. Toutefois, puisque la TDM est substantiellement 
plus coûteuse et complexe, la radiographie pulmonaire simple 
est habituellement privilégiée (35). La TDM est employée 
lorsque les résultats de la radiographie signalent une 
pathologie plus complexe.
Figure 5 — Diagnostic de la cholécystite aiguë (27)
Échographie
Prise en charge appropriée
TDM ou médecine nucléaire
TDM ou médecine nucléaire
Envisager d’autres diagnostics
Résultats positifs
Résultats non concluants
Résultats négatifs
Douleur aiguë au quadrant supérieur droit
21
Apparition aiguë de toux et de �ièvre
Radiographie pulmonaire
TDM (bronchoscopie)
TDM (bronchoscopie)
Radiographie 
pulmonaire de suivi
Résolution Aucun autre examen
Aucune 
résolution
Prise en charge appropriée
Consolidation avec complications
Aspect normal
Consolidation
Figure 6 — Diagnostic en cas de toux accompagnée de fièvre (33)
22
PREMIÈRE PARTIE – CHOIX MULTIPLES 
1) Parmi les modalités d’imagerie ci-dessous, lesquelles
ne font pas appel aux rayonnements ionisants? 
Choisir toutes les réponses applicables.
a. Mammographie b. Radiographie avec film
c. TDM d. TEPU
e. Radioscopie f. IRM
g. Échographie h. Radiographie numérique
i. TEP
2) Parmi les modalités d’imagerie ci-dessous, 
lesquelles reposent sur les rayons X? 
Choisir toutes les réponses applicables.
a. Mammographie b. Radiographie avec film
c. TDM d. TEPU
e. Radioscopie f. IRM
g. Échographie h. Radiographie numérique
i. TEP
3) Les rayons X et les rayons gamma sont deux 
exemples de rayonnements ionisants.
a. Vrai b. Faux
4) Les rayons X sont utilisés dans les techniques de 
médecine nucléaire (TEP et TEPU).
a. Vrai b. Faux
5) Un patient ayant subi un examen d’imagerie par rayons X 
demeure radioactif après l’examen.
a. Vrai b. Faux
6) La CIPR classe les effets biologiques des rayonnements 
ionisants en deux catégories : déterministes et stochastiques. 
Les effets stochastiques sont :
a. Les effets dont la gravité augmente avec la dose.
b. Les effets dont la probabilité augmente avec la dose.
7) Lorsqu’un patient subit un examen d’imagerie par 
rayonnements ionisants, les effets déterministes 
sont la principale cause de préoccupation. 
a. Vrai b. Faux
8) La dose efficace moyenne de rayonnement naturel 
mesurée en un an est de l’ordre de :
a. 1 à 10 mSv b. 1 à 10 Sv
9) Si vous prenez les mesures appropriées pour éviter 
toute exposition inutile des patients aux rayonnements 
ionisants, vous suivez le principe :
a. CIPR b. BEIR
c. ALARA d. LAR
10) Si un patient a des agrafes pour anévrisme, lesquelles des 
modalités d’imagerie suivantes devrait-on éviter?
 a. TDM b. IRM
12. ANNEXE 2 : TEST SUR LES PRINCIPAUX CONCEPTS
DEUXIÈME PARTIE – RÉPONSES COURTES
11) Expliquez pourquoi les poumons apparaissent en noir sur une radiographie, tandis que les os apparaissent en blanc.
12) Énumérez quelques façons de limiter l’exposition aux rayonnements.
13) Résumez les effets in utero des rayonnements.
14) Expliquez dans quelles régions l’échographie n’est pas la méthode d’imagerie à privilégier.
23
RÉPONSES :
1) f. IRM
g. Échographie (voir la section 2)
2) a. Mammographie 
b. Radiographie avec film
c. TDM
e. Radioscopie
h. Radiographie numérique (voir la section 2)
3) a. Vrai (voir la section 1)
4) b. Faux (voir la section 2)
5) b. Faux (voir la section 2)
6) b. Les effets dont la probabilité augmente avec la dose. (voir la section 3.2)
7) b. Faux (voir la section 3.2)
8) a. 1 à 10 mSv (voir la section 3.3)
9) c. ALARA (voir la section 3.3)
10) b. IRM (voir la section 6.2)
11) (voir la section 2)
12) (voir la section 4)
13) (voir la section 5)
14) (voir la section 6.1)
24
Références
1. Bushberg JT. ‘The essential physics of medical imaging’. Lippincott Williams & Wilkins; 2002.
2. Cherry SR, Sorenson JA, Phelps ME. ‘Physics in Nuclear Medicine’, 3rd ed. WB Saunders; 2003. 
3. Hsiao E, Rybicki F, Steigner M. ‘CT Coronary Angiography: 256-Slice and 320-Detector Row Scanners’. 
Current Cardiology Reports 2010 Jan;12(1):68-75.
4. Bankman IN. ‘Handbook of medical imaging: processing and analysis’. Academic Press; 2000.
5. Hall EJ, Giaccia AJ. ‘Radiobiology for the radiologist’. Lippincott Williams & Wilkins; 2006.
6. Huda W. ‘What ER radiologists need to know about radiation risks.’ Emergency Radiology 2009;16(5):335-341.
7. ICRP, 2007. ‘The 2007 Recommendations of the International Commission on Radiological Protection’. ICRP Publication 103. Ann. 
ICRP 37 (2-4). (see http://www.icrp.org/publication.asp?id=ICRP%20Publication%20103)
8. Committee to Assess Health Risks from Exposure to Low Levels of Ionizing Radiation, National Research Council. ‘Health Risks from 
Exposure to Low Levels of Ionizing Radiation: BEIR VII Phase 2’. Washington, D.C.: The National Academies Press; 2006.
9. Tubiana M. Dose-effect relationship and estimation of the carcinogenic effects of low doses of ionizing radiation: 
the joint report of the Académie des Sciences (Paris) and of the Académie Nationale de Médecine. Int. J. Radiat. 
Oncol. Biol. Phys 2005 Oct;63(2):317-319.
10. ICRP, 2007. ‘Radiological Protection in Medicine’. ICRP Publication 105. Ann. ICRP 37 (6).
(see http://www.icrp.org/publication.asp?id=ICRP%20Publication%20105)
11. Thakur Y, Bjarnason TA, Chakraborty S, Liu P, O’Malley ME, Coulden R, Noga M, Mason A, Mayo J. Canadian Association of 
Radiologists Radiation Protection Working Group: ‘Review of Radiation Units and the Use of Computed Tomography Dose 
Indicators in Canada’. Canadian Association of Radiologists Journal <http://www.carjonline.org/article/S0846-
5371%2811%2900204-X/fulltext> 2012; 1-4
12.Grasty RL, LaMarre JR. ‘The annual effective dose from natural sources of ionizing radiation in Canada’. Radiation Protection 
Dosimetry 2004; 108(3): 215-226
13. National Council on Radiation Protection and Measurements (NCRP). ‘Ionizing radiation exposure of the populations of the United 
States Bethesda, MD:’ NCRP report 160, 2009.
14. Radiology Society of North America. Safety in medical imaging procedures. Oak Brook: Radiology Info, 2009. Accessed Jan 14, 
2009, from <http://www.radiologyinfo.org/en/safety/index.cfm?pg=sfty_xray>
15. K Strubler. Cancer treatment: risks of medical radiation. Baltimore: Greater Baltimore Medical Center (GBMC), 2008. Accessed Jan. 
16, 2009, from <http://www.gbmc.org/cancer/radoncology/risksofmedicalradiation.cfm>
16. Cousins C, Sharp C. ‘Medical interventional procedures – reducing the radiation risks.’ Clin Radiol, 2004; 54: 468-73.
17. Hale J. ‘X-ray protection.’ in Taveras JM, Ferrucci JT (eds). Radiology diagnosis-imaging-intervention. Revised ed. Lippincott 
Company: Philadelphia, 1992.
18. Vañó E, González L, Guiebelalde E, et al. ‘Radiation exposure to medical staff in interventional and cardiac radiology.’ Br J Radiol, 
1998; 71: 954-60
25
19. Cohen KR, Nulman I, Abramow-Newerly M, et al. ‘Diagnostic radiation in pregnancy: perception versus true risks.’ 
J Obstet Gynaecol Can, 2006; 28: 43-8.
20. Ratnapalan S, Bentur Y, Koren G. ‘Doctor, will that x-ray harm my unborn child?’ CMAJ, 2008; 179, (12): 1293-6
21. De Santis M, Di Gianantonio E, Straface G, Cavaliere A, Caruso A, Schiavon F, Berletti R, Clementi M. ‘Ionizing radiations in 
pregnancy and teratogenesis: A review of literature’. Reproductive Toxicology, 2005;20(3):323-329.
22. Bentur Y. ‘Ionizing and non-ionizing radiation in pregnancy’. In: Medication safety in pregnancy and breastfeeding. Philadelphia 
(PA): MacGraw Hill; 2007. p. 221-48.
23. Center for Disease Control and Prevention (CDC). Prenatal radiation exposure: a fact sheet for physicians. Atlanta: CDC, 2005. 
Accessed Jan 12, 2009, from <http://www.bt.cdc.gov/radiation/prenatalphysician.asp>.
24. Bentur Y, Norlatsch N, Koren G. ‘Exposure to ionizing radiation during pregnancy: perception of teratogenic risk 
and outcome.’ Teratology, 1991; 43: 109-12.
25. Ratnapalan S, Bona N, Chandra K, et al. ‘Physicians’ perceptions of teratogenic risk associated with radiography 
and CT during early pregnancy.’ AJR, 2004; 182: 1107-1109.
26. Shiralkar S, Rennie A, Snow M, et al. ‘Doctor’s knowledge of radiation exposure; questionnaire study.’ BMJ, 2003; 327: 371-2.
27. The Royal Australian and New Zealand College of Radiologists. Imaging Guidelines. 4th edn. Surrey Hills: National Library of 
Australia Cataloguing-in-Publication Data, 2001
28. Merritt CB. ‘Ultrasound safety: what are the issues?’ Radiology, 1989; 173: 304-6.
29. Formica D, Silvestri S. ‘Biological effects of exposure to magnetic resonance imaging: an overview.’ Biomed Eng Online, 2004; 3, 
(11). Accessed 15 Jan 2009, from <http://www.biomedical-engineering-online.com/content/3/1/11
30. Bittner JG, et al. ‘Resident training in flexible gastrointestinal endoscopy: a review of current issues and options’. 
J Surg Educ, 2007; 64, (6): 399-409.
31. Greene FL, Nordness PJ. ‘Laparoscopy for the diagnosis and staging of intra-abdominal malignancies.’ In Zucker KA (ed), Surgical 
Laparoscopy. 2nd edn. Philadelphia: Lippincott Williams and Wilkins, 2001. pp 103-12
32. The Evidence-Based Radiology Working Group. ‘Evidence-based radiology: a new approach to the practice of 
radiology.’ Radiology, 2001; 220: 566-575.
33. American College of Radiology. ‘ACCR appropriateness criteria.’ Radiology, 2000; 215 (Suppl): 1-1511.
34. Black ER, Bordley DR, Tape TG, Panzer RJ (eds). ‘Diagnostic Strategies for Common Medical Problems’. 2nd ed. Philadelphia: 
American College of Physicians, 1999.
35. Katz DS, Leung AN. ‘Radiology of pneumonia.’ Clin Chest Med, 1999; 20 (3): 549-62
613 860-3111 • INFO@CAR.CA • WWW.CAR.C"""

chunks = chunk_text(document)

for chunk in chunks:
    response = requests.post(url, json={"model": "llama3.2", "prompt": chunk})
    tokens = response.json()
    print(tokens)


async def send_get_request(url, key=None, user: UserModel = None):
    timeout = aiohttp.ClientTimeout(total=AIOHTTP_CLIENT_TIMEOUT_MODEL_LIST)
    try:
        async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
            async with session.get(
                url,
                headers={
                    "Content-Type": "application/json",
                    **({"Authorization": f"Bearer {key}"} if key else {}),
                    **(
                        {
                            "X-OpenWebUI-User-Name": user.name,
                            "X-OpenWebUI-User-Id": user.id,
                            "X-OpenWebUI-User-Email": user.email,
                            "X-OpenWebUI-User-Role": user.role,
                        }
                        if ENABLE_FORWARD_USER_INFO_HEADERS and user
                        else {}
                    ),
                },
            ) as response:
                return await response.json()
    except Exception as e:
        # Handle connection error here
        log.error(f"Connection error: {e}")
        return None


async def cleanup_response(
    response: Optional[aiohttp.ClientResponse],
    session: Optional[aiohttp.ClientSession],
):
    if response:
        response.close()
    if session:
        await session.close()


async def send_post_request(
    url: str,
    payload: Union[str, bytes],
    stream: bool = True,
    key: Optional[str] = None,
    content_type: Optional[str] = None,
    user: UserModel = None,
):

    r = None
    try:
        session = aiohttp.ClientSession(
            trust_env=True, timeout=aiohttp.ClientTimeout(total=AIOHTTP_CLIENT_TIMEOUT)
        )

        r = await session.post(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {key}"} if key else {}),
                **(
                    {
                        "X-OpenWebUI-User-Name": user.name,
                        "X-OpenWebUI-User-Id": user.id,
                        "X-OpenWebUI-User-Email": user.email,
                        "X-OpenWebUI-User-Role": user.role,
                    }
                    if ENABLE_FORWARD_USER_INFO_HEADERS and user
                    else {}
                ),
            },
        )
        r.raise_for_status()

        if stream:
            response_headers = dict(r.headers)

            if content_type:
                response_headers["Content-Type"] = content_type

            return StreamingResponse(
                r.content,
                status_code=r.status,
                headers=response_headers,
                background=BackgroundTask(
                    cleanup_response, response=r, session=session
                ),
            )
        else:
            res = await r.json()
            await cleanup_response(r, session)
            return res

    except Exception as e:
        detail = None

        if r is not None:
            try:
                res = await r.json()
                if "error" in res:
                    detail = f"Ollama: {res.get('error', 'Unknown error')}"
            except Exception:
                detail = f"Ollama: {e}"

        raise HTTPException(
            status_code=r.status if r else 500,
            detail=detail if detail else "Open WebUI: Server Connection Error",
        )


def get_api_key(idx, url, configs):
    parsed_url = urlparse(url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    return configs.get(str(idx), configs.get(base_url, {})).get(
        "key", None
    )  # Legacy support


##########################################
#
# API routes
#
##########################################

router = APIRouter()


@router.head("/")
@router.get("/")
async def get_status():
    return {"status": True}


class ConnectionVerificationForm(BaseModel):
    url: str
    key: Optional[str] = None


@router.post("/verify")
async def verify_connection(
    form_data: ConnectionVerificationForm, user=Depends(get_admin_user)
):
    url = form_data.url
    key = form_data.key

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=AIOHTTP_CLIENT_TIMEOUT_MODEL_LIST)
    ) as session:
        try:
            async with session.get(
                f"{url}/api/version",
                headers={
                    **({"Authorization": f"Bearer {key}"} if key else {}),
                    **(
                        {
                            "X-OpenWebUI-User-Name": user.name,
                            "X-OpenWebUI-User-Id": user.id,
                            "X-OpenWebUI-User-Email": user.email,
                            "X-OpenWebUI-User-Role": user.role,
                        }
                        if ENABLE_FORWARD_USER_INFO_HEADERS and user
                        else {}
                    ),
                },
            ) as r:
                if r.status != 200:
                    detail = f"HTTP Error: {r.status}"
                    res = await r.json()

                    if "error" in res:
                        detail = f"External Error: {res['error']}"
                    raise Exception(detail)

                data = await r.json()
                return data
        except aiohttp.ClientError as e:
            log.exception(f"Client error: {str(e)}")
            raise HTTPException(
                status_code=500, detail="Open WebUI: Server Connection Error"
            )
        except Exception as e:
            log.exception(f"Unexpected error: {e}")
            error_detail = f"Unexpected error: {str(e)}"
            raise HTTPException(status_code=500, detail=error_detail)


@router.get("/config")
async def get_config(request: Request, user=Depends(get_admin_user)):
    return {
        "ENABLE_OLLAMA_API": request.app.state.config.ENABLE_OLLAMA_API,
        "OLLAMA_BASE_URLS": request.app.state.config.OLLAMA_BASE_URLS,
        "OLLAMA_API_CONFIGS": request.app.state.config.OLLAMA_API_CONFIGS,
    }


class OllamaConfigForm(BaseModel):
    ENABLE_OLLAMA_API: Optional[bool] = None
    OLLAMA_BASE_URLS: list[str]
    OLLAMA_API_CONFIGS: dict


@router.post("/config/update")
async def update_config(
    request: Request, form_data: OllamaConfigForm, user=Depends(get_admin_user)
):
    request.app.state.config.ENABLE_OLLAMA_API = form_data.ENABLE_OLLAMA_API

    request.app.state.config.OLLAMA_BASE_URLS = form_data.OLLAMA_BASE_URLS
    request.app.state.config.OLLAMA_API_CONFIGS = form_data.OLLAMA_API_CONFIGS

    # Remove the API configs that are not in the API URLS
    keys = list(map(str, range(len(request.app.state.config.OLLAMA_BASE_URLS))))
    request.app.state.config.OLLAMA_API_CONFIGS = {
        key: value
        for key, value in request.app.state.config.OLLAMA_API_CONFIGS.items()
        if key in keys
    }

    return {
        "ENABLE_OLLAMA_API": request.app.state.config.ENABLE_OLLAMA_API,
        "OLLAMA_BASE_URLS": request.app.state.config.OLLAMA_BASE_URLS,
        "OLLAMA_API_CONFIGS": request.app.state.config.OLLAMA_API_CONFIGS,
    }


@cached(ttl=3)
async def get_all_models(request: Request, user: UserModel = None):
    log.info("get_all_models()")
    if request.app.state.config.ENABLE_OLLAMA_API:
        request_tasks = []
        for idx, url in enumerate(request.app.state.config.OLLAMA_BASE_URLS):
            if (str(idx) not in request.app.state.config.OLLAMA_API_CONFIGS) and (
                url not in request.app.state.config.OLLAMA_API_CONFIGS  # Legacy support
            ):
                request_tasks.append(send_get_request(f"{url}/api/tags", user=user))
            else:
                api_config = request.app.state.config.OLLAMA_API_CONFIGS.get(
                    str(idx),
                    request.app.state.config.OLLAMA_API_CONFIGS.get(
                        url, {}
                    ),  # Legacy support
                )

                enable = api_config.get("enable", True)
                key = api_config.get("key", None)

                if enable:
                    request_tasks.append(
                        send_get_request(f"{url}/api/tags", key, user=user)
                    )
                else:
                    request_tasks.append(asyncio.ensure_future(asyncio.sleep(0, None)))

        responses = await asyncio.gather(*request_tasks)

        for idx, response in enumerate(responses):
            if response:
                url = request.app.state.config.OLLAMA_BASE_URLS[idx]
                api_config = request.app.state.config.OLLAMA_API_CONFIGS.get(
                    str(idx),
                    request.app.state.config.OLLAMA_API_CONFIGS.get(
                        url, {}
                    ),  # Legacy support
                )

                prefix_id = api_config.get("prefix_id", None)
                model_ids = api_config.get("model_ids", [])

                if len(model_ids) != 0 and "models" in response:
                    response["models"] = list(
                        filter(
                            lambda model: model["model"] in model_ids,
                            response["models"],
                        )
                    )

                if prefix_id:
                    for model in response.get("models", []):
                        model["model"] = f"{prefix_id}.{model['model']}"

        def merge_models_lists(model_lists):
            merged_models = {}

            for idx, model_list in enumerate(model_lists):
                if model_list is not None:
                    for model in model_list:
                        id = model["model"]
                        if id not in merged_models:
                            model["urls"] = [idx]
                            merged_models[id] = model
                        else:
                            merged_models[id]["urls"].append(idx)

            return list(merged_models.values())

        models = {
            "models": merge_models_lists(
                map(
                    lambda response: response.get("models", []) if response else None,
                    responses,
                )
            )
        }

    else:
        models = {"models": []}

    request.app.state.OLLAMA_MODELS = {
        model["model"]: model for model in models["models"]
    }
    return models


async def get_filtered_models(models, user):
    # Filter models based on user access control
    filtered_models = []
    for model in models.get("models", []):
        model_info = Models.get_model_by_id(model["model"])
        if model_info:
            if user.id == model_info.user_id or has_access(
                user.id, type="read", access_control=model_info.access_control
            ):
                filtered_models.append(model)
    return filtered_models


@router.get("/api/tags")
@router.get("/api/tags/{url_idx}")
async def get_ollama_tags(
    request: Request, url_idx: Optional[int] = None, user=Depends(get_verified_user)
):
    models = []

    if url_idx is None:
        models = await get_all_models(request, user=user)
    else:
        url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
        key = get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS)

        r = None
        try:
            r = requests.request(
                method="GET",
                url=f"{url}/api/tags",
                headers={
                    **({"Authorization": f"Bearer {key}"} if key else {}),
                    **(
                        {
                            "X-OpenWebUI-User-Name": user.name,
                            "X-OpenWebUI-User-Id": user.id,
                            "X-OpenWebUI-User-Email": user.email,
                            "X-OpenWebUI-User-Role": user.role,
                        }
                        if ENABLE_FORWARD_USER_INFO_HEADERS and user
                        else {}
                    ),
                },
            )
            r.raise_for_status()

            models = r.json()
        except Exception as e:
            log.exception(e)

            detail = None
            if r is not None:
                try:
                    res = r.json()
                    if "error" in res:
                        detail = f"Ollama: {res['error']}"
                except Exception:
                    detail = f"Ollama: {e}"

            raise HTTPException(
                status_code=r.status_code if r else 500,
                detail=detail if detail else "Open WebUI: Server Connection Error",
            )

    if user.role == "user" and not BYPASS_MODEL_ACCESS_CONTROL:
        models["models"] = await get_filtered_models(models, user)

    return models


@router.get("/api/version")
@router.get("/api/version/{url_idx}")
async def get_ollama_versions(request: Request, url_idx: Optional[int] = None):
    if request.app.state.config.ENABLE_OLLAMA_API:
        if url_idx is None:
            # returns lowest version
            request_tasks = [
                send_get_request(
                    f"{url}/api/version",
                    request.app.state.config.OLLAMA_API_CONFIGS.get(
                        str(idx),
                        request.app.state.config.OLLAMA_API_CONFIGS.get(
                            url, {}
                        ),  # Legacy support
                    ).get("key", None),
                )
                for idx, url in enumerate(request.app.state.config.OLLAMA_BASE_URLS)
            ]
            responses = await asyncio.gather(*request_tasks)
            responses = list(filter(lambda x: x is not None, responses))

            if len(responses) > 0:
                lowest_version = min(
                    responses,
                    key=lambda x: tuple(
                        map(int, re.sub(r"^v|-.*", "", x["version"]).split("."))
                    ),
                )

                return {"version": lowest_version["version"]}
            else:
                raise HTTPException(
                    status_code=500,
                    detail=ERROR_MESSAGES.OLLAMA_NOT_FOUND,
                )
        else:
            url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]

            r = None
            try:
                r = requests.request(method="GET", url=f"{url}/api/version")
                r.raise_for_status()

                return r.json()
            except Exception as e:
                log.exception(e)

                detail = None
                if r is not None:
                    try:
                        res = r.json()
                        if "error" in res:
                            detail = f"Ollama: {res['error']}"
                    except Exception:
                        detail = f"Ollama: {e}"

                raise HTTPException(
                    status_code=r.status_code if r else 500,
                    detail=detail if detail else "Open WebUI: Server Connection Error",
                )
    else:
        return {"version": False}


@router.get("/api/ps")
async def get_ollama_loaded_models(request: Request, user=Depends(get_verified_user)):
    """
    List models that are currently loaded into Ollama memory, and which node they are loaded on.
    """
    if request.app.state.config.ENABLE_OLLAMA_API:
        request_tasks = [
            send_get_request(
                f"{url}/api/ps",
                request.app.state.config.OLLAMA_API_CONFIGS.get(
                    str(idx),
                    request.app.state.config.OLLAMA_API_CONFIGS.get(
                        url, {}
                    ),  # Legacy support
                ).get("key", None),
                user=user,
            )
            for idx, url in enumerate(request.app.state.config.OLLAMA_BASE_URLS)
        ]
        responses = await asyncio.gather(*request_tasks)

        return dict(zip(request.app.state.config.OLLAMA_BASE_URLS, responses))
    else:
        return {}


class ModelNameForm(BaseModel):
    name: str


@router.post("/api/pull")
@router.post("/api/pull/{url_idx}")
async def pull_model(
    request: Request,
    form_data: ModelNameForm,
    url_idx: int = 0,
    user=Depends(get_admin_user),
):
    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
    log.info(f"url: {url}")

    # Admin should be able to pull models from any source
    payload = {**form_data.model_dump(exclude_none=True), "insecure": True}

    return await send_post_request(
        url=f"{url}/api/pull",
        payload=json.dumps(payload),
        key=get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS),
        user=user,
    )


class PushModelForm(BaseModel):
    name: str
    insecure: Optional[bool] = None
    stream: Optional[bool] = None


@router.delete("/api/push")
@router.delete("/api/push/{url_idx}")
async def push_model(
    request: Request,
    form_data: PushModelForm,
    url_idx: Optional[int] = None,
    user=Depends(get_admin_user),
):
    if url_idx is None:
        await get_all_models(request, user=user)
        models = request.app.state.OLLAMA_MODELS

        if form_data.name in models:
            url_idx = models[form_data.name]["urls"][0]
        else:
            raise HTTPException(
                status_code=400,
                detail=ERROR_MESSAGES.MODEL_NOT_FOUND(form_data.name),
            )

    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
    log.debug(f"url: {url}")

    return await send_post_request(
        url=f"{url}/api/push",
        payload=form_data.model_dump_json(exclude_none=True).encode(),
        key=get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS),
        user=user,
    )


class CreateModelForm(BaseModel):
    model: Optional[str] = None
    stream: Optional[bool] = None
    path: Optional[str] = None

    model_config = ConfigDict(extra="allow")


@router.post("/api/create")
@router.post("/api/create/{url_idx}")
async def create_model(
    request: Request,
    form_data: CreateModelForm,
    url_idx: int = 0,
    user=Depends(get_admin_user),
):
    log.debug(f"form_data: {form_data}")
    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]

    return await send_post_request(
        url=f"{url}/api/create",
        payload=form_data.model_dump_json(exclude_none=True).encode(),
        key=get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS),
        user=user,
    )


class CopyModelForm(BaseModel):
    source: str
    destination: str


@router.post("/api/copy")
@router.post("/api/copy/{url_idx}")
async def copy_model(
    request: Request,
    form_data: CopyModelForm,
    url_idx: Optional[int] = None,
    user=Depends(get_admin_user),
):
    if url_idx is None:
        await get_all_models(request, user=user)
        models = request.app.state.OLLAMA_MODELS

        if form_data.source in models:
            url_idx = models[form_data.source]["urls"][0]
        else:
            raise HTTPException(
                status_code=400,
                detail=ERROR_MESSAGES.MODEL_NOT_FOUND(form_data.source),
            )

    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
    key = get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS)

    try:
        r = requests.request(
            method="POST",
            url=f"{url}/api/copy",
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {key}"} if key else {}),
                **(
                    {
                        "X-OpenWebUI-User-Name": user.name,
                        "X-OpenWebUI-User-Id": user.id,
                        "X-OpenWebUI-User-Email": user.email,
                        "X-OpenWebUI-User-Role": user.role,
                    }
                    if ENABLE_FORWARD_USER_INFO_HEADERS and user
                    else {}
                ),
            },
            data=form_data.model_dump_json(exclude_none=True).encode(),
        )
        r.raise_for_status()

        log.debug(f"r.text: {r.text}")
        return True
    except Exception as e:
        log.exception(e)

        detail = None
        if r is not None:
            try:
                res = r.json()
                if "error" in res:
                    detail = f"Ollama: {res['error']}"
            except Exception:
                detail = f"Ollama: {e}"

        raise HTTPException(
            status_code=r.status_code if r else 500,
            detail=detail if detail else "Open WebUI: Server Connection Error",
        )


@router.delete("/api/delete")
@router.delete("/api/delete/{url_idx}")
async def delete_model(
    request: Request,
    form_data: ModelNameForm,
    url_idx: Optional[int] = None,
    user=Depends(get_admin_user),
):
    if url_idx is None:
        await get_all_models(request, user=user)
        models = request.app.state.OLLAMA_MODELS

        if form_data.name in models:
            url_idx = models[form_data.name]["urls"][0]
        else:
            raise HTTPException(
                status_code=400,
                detail=ERROR_MESSAGES.MODEL_NOT_FOUND(form_data.name),
            )

    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
    key = get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS)

    try:
        r = requests.request(
            method="DELETE",
            url=f"{url}/api/delete",
            data=form_data.model_dump_json(exclude_none=True).encode(),
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {key}"} if key else {}),
                **(
                    {
                        "X-OpenWebUI-User-Name": user.name,
                        "X-OpenWebUI-User-Id": user.id,
                        "X-OpenWebUI-User-Email": user.email,
                        "X-OpenWebUI-User-Role": user.role,
                    }
                    if ENABLE_FORWARD_USER_INFO_HEADERS and user
                    else {}
                ),
            },
        )
        r.raise_for_status()

        log.debug(f"r.text: {r.text}")
        return True
    except Exception as e:
        log.exception(e)

        detail = None
        if r is not None:
            try:
                res = r.json()
                if "error" in res:
                    detail = f"Ollama: {res['error']}"
            except Exception:
                detail = f"Ollama: {e}"

        raise HTTPException(
            status_code=r.status_code if r else 500,
            detail=detail if detail else "Open WebUI: Server Connection Error",
        )


@router.post("/api/show")
async def show_model_info(
    request: Request, form_data: ModelNameForm, user=Depends(get_verified_user)
):
    await get_all_models(request, user=user)
    models = request.app.state.OLLAMA_MODELS

    if form_data.name not in models:
        raise HTTPException(
            status_code=400,
            detail=ERROR_MESSAGES.MODEL_NOT_FOUND(form_data.name),
        )

    url_idx = random.choice(models[form_data.name]["urls"])

    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
    key = get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS)

    try:
        r = requests.request(
            method="POST",
            url=f"{url}/api/show",
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {key}"} if key else {}),
                **(
                    {
                        "X-OpenWebUI-User-Name": user.name,
                        "X-OpenWebUI-User-Id": user.id,
                        "X-OpenWebUI-User-Email": user.email,
                        "X-OpenWebUI-User-Role": user.role,
                    }
                    if ENABLE_FORWARD_USER_INFO_HEADERS and user
                    else {}
                ),
            },
            data=form_data.model_dump_json(exclude_none=True).encode(),
        )
        r.raise_for_status()

        return r.json()
    except Exception as e:
        log.exception(e)

        detail = None
        if r is not None:
            try:
                res = r.json()
                if "error" in res:
                    detail = f"Ollama: {res['error']}"
            except Exception:
                detail = f"Ollama: {e}"

        raise HTTPException(
            status_code=r.status_code if r else 500,
            detail=detail if detail else "Open WebUI: Server Connection Error",
        )


class GenerateEmbedForm(BaseModel):
    model: str
    input: list[str] | str
    truncate: Optional[bool] = None
    options: Optional[dict] = None
    keep_alive: Optional[Union[int, str]] = None


@router.post("/api/embed")
@router.post("/api/embed/{url_idx}")
async def embed(
    request: Request,
    form_data: GenerateEmbedForm,
    url_idx: Optional[int] = None,
    user=Depends(get_verified_user),
):
    log.info(f"generate_ollama_batch_embeddings {form_data}")

    if url_idx is None:
        await get_all_models(request, user=user)
        models = request.app.state.OLLAMA_MODELS

        model = form_data.model

        if ":" not in model:
            model = f"{model}:latest"

        if model in models:
            url_idx = random.choice(models[model]["urls"])
        else:
            raise HTTPException(
                status_code=400,
                detail=ERROR_MESSAGES.MODEL_NOT_FOUND(form_data.model),
            )

    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
    key = get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS)

    try:
        r = requests.request(
            method="POST",
            url=f"{url}/api/embed",
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {key}"} if key else {}),
                **(
                    {
                        "X-OpenWebUI-User-Name": user.name,
                        "X-OpenWebUI-User-Id": user.id,
                        "X-OpenWebUI-User-Email": user.email,
                        "X-OpenWebUI-User-Role": user.role,
                    }
                    if ENABLE_FORWARD_USER_INFO_HEADERS and user
                    else {}
                ),
            },
            data=form_data.model_dump_json(exclude_none=True).encode(),
        )
        r.raise_for_status()

        data = r.json()
        return data
    except Exception as e:
        log.exception(e)

        detail = None
        if r is not None:
            try:
                res = r.json()
                if "error" in res:
                    detail = f"Ollama: {res['error']}"
            except Exception:
                detail = f"Ollama: {e}"

        raise HTTPException(
            status_code=r.status_code if r else 500,
            detail=detail if detail else "Open WebUI: Server Connection Error",
        )


class GenerateEmbeddingsForm(BaseModel):
    model: str
    prompt: str
    options: Optional[dict] = None
    keep_alive: Optional[Union[int, str]] = None


@router.post("/api/embeddings")
@router.post("/api/embeddings/{url_idx}")
async def embeddings(
    request: Request,
    form_data: GenerateEmbeddingsForm,
    url_idx: Optional[int] = None,
    user=Depends(get_verified_user),
):
    log.info(f"generate_ollama_embeddings {form_data}")

    if url_idx is None:
        await get_all_models(request, user=user)
        models = request.app.state.OLLAMA_MODELS

        model = form_data.model

        if ":" not in model:
            model = f"{model}:latest"

        if model in models:
            url_idx = random.choice(models[model]["urls"])
        else:
            raise HTTPException(
                status_code=400,
                detail=ERROR_MESSAGES.MODEL_NOT_FOUND(form_data.model),
            )

    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
    key = get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS)

    try:
        r = requests.request(
            method="POST",
            url=f"{url}/api/embeddings",
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {key}"} if key else {}),
                **(
                    {
                        "X-OpenWebUI-User-Name": user.name,
                        "X-OpenWebUI-User-Id": user.id,
                        "X-OpenWebUI-User-Email": user.email,
                        "X-OpenWebUI-User-Role": user.role,
                    }
                    if ENABLE_FORWARD_USER_INFO_HEADERS and user
                    else {}
                ),
            },
            data=form_data.model_dump_json(exclude_none=True).encode(),
        )
        r.raise_for_status()

        data = r.json()
        return data
    except Exception as e:
        log.exception(e)

        detail = None
        if r is not None:
            try:
                res = r.json()
                if "error" in res:
                    detail = f"Ollama: {res['error']}"
            except Exception:
                detail = f"Ollama: {e}"

        raise HTTPException(
            status_code=r.status_code if r else 500,
            detail=detail if detail else "Open WebUI: Server Connection Error",
        )


class GenerateCompletionForm(BaseModel):
    model: str
    prompt: str
    suffix: Optional[str] = None
    images: Optional[list[str]] = None
    format: Optional[str] = None
    options: Optional[dict] = None
    system: Optional[str] = None
    template: Optional[str] = None
    context: Optional[list[int]] = None
    stream: Optional[bool] = True
    raw: Optional[bool] = None
    keep_alive: Optional[Union[int, str]] = None


@router.post("/api/generate")
@router.post("/api/generate/{url_idx}")
async def generate_completion(
    request: Request,
    form_data: GenerateCompletionForm,
    url_idx: Optional[int] = None,
    user=Depends(get_verified_user),
):
    if url_idx is None:
        await get_all_models(request, user=user)
        models = request.app.state.OLLAMA_MODELS

        model = form_data.model

        if ":" not in model:
            model = f"{model}:latest"

        if model in models:
            url_idx = random.choice(models[model]["urls"])
        else:
            raise HTTPException(
                status_code=400,
                detail=ERROR_MESSAGES.MODEL_NOT_FOUND(form_data.model),
            )

    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
    api_config = request.app.state.config.OLLAMA_API_CONFIGS.get(
        str(url_idx),
        request.app.state.config.OLLAMA_API_CONFIGS.get(url, {}),  # Legacy support
    )

    prefix_id = api_config.get("prefix_id", None)
    if prefix_id:
        form_data.model = form_data.model.replace(f"{prefix_id}.", "")

    return await send_post_request(
        url=f"{url}/api/generate",
        payload=form_data.model_dump_json(exclude_none=True).encode(),
        key=get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS),
        user=user,
    )


class ChatMessage(BaseModel):
    role: str
    content: Optional[str] = None
    tool_calls: Optional[list[dict]] = None
    images: Optional[list[str]] = None

    @validator("content", pre=True)
    @classmethod
    def check_at_least_one_field(cls, field_value, values, **kwargs):
        # Raise an error if both 'content' and 'tool_calls' are None
        if field_value is None and (
            "tool_calls" not in values or values["tool_calls"] is None
        ):
            raise ValueError(
                "At least one of 'content' or 'tool_calls' must be provided"
            )

        return field_value


class GenerateChatCompletionForm(BaseModel):
    model: str
    messages: list[ChatMessage]
    format: Optional[Union[dict, str]] = None
    options: Optional[dict] = None
    template: Optional[str] = None
    stream: Optional[bool] = True
    keep_alive: Optional[Union[int, str]] = None
    tools: Optional[list[dict]] = None


async def get_ollama_url(request: Request, model: str, url_idx: Optional[int] = None):
    if url_idx is None:
        models = request.app.state.OLLAMA_MODELS
        if model not in models:
            raise HTTPException(
                status_code=400,
                detail=ERROR_MESSAGES.MODEL_NOT_FOUND(model),
            )
        url_idx = random.choice(models[model].get("urls", []))
    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
    return url, url_idx


@router.post("/api/chat")
@router.post("/api/chat/{url_idx}")
async def generate_chat_completion(
    request: Request,
    form_data: dict,
    url_idx: Optional[int] = None,
    user=Depends(get_verified_user),
    bypass_filter: Optional[bool] = False,
):
    if BYPASS_MODEL_ACCESS_CONTROL:
        bypass_filter = True

    metadata = form_data.pop("metadata", None)
    try:
        form_data = GenerateChatCompletionForm(**form_data)
    except Exception as e:
        log.exception(e)
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

    payload = {**form_data.model_dump(exclude_none=True)}
    if "metadata" in payload:
        del payload["metadata"]

    model_id = payload["model"]
    model_info = Models.get_model_by_id(model_id)

    if model_info:
        if model_info.base_model_id:
            payload["model"] = model_info.base_model_id

        params = model_info.params.model_dump()

        if params:
            if payload.get("options") is None:
                payload["options"] = {}

            payload["options"] = apply_model_params_to_body_ollama(
                params, payload["options"]
            )
            payload = apply_model_system_prompt_to_body(params, payload, metadata, user)

        # Check if user has access to the model
        if not bypass_filter and user.role == "user":
            if not (
                user.id == model_info.user_id
                or has_access(
                    user.id, type="read", access_control=model_info.access_control
                )
            ):
                raise HTTPException(
                    status_code=403,
                    detail="Model not found",
                )
    elif not bypass_filter:
        if user.role != "admin":
            raise HTTPException(
                status_code=403,
                detail="Model not found",
            )

    if ":" not in payload["model"]:
        payload["model"] = f"{payload['model']}:latest"

    url, url_idx = await get_ollama_url(request, payload["model"], url_idx)
    api_config = request.app.state.config.OLLAMA_API_CONFIGS.get(
        str(url_idx),
        request.app.state.config.OLLAMA_API_CONFIGS.get(url, {}),  # Legacy support
    )

    prefix_id = api_config.get("prefix_id", None)
    if prefix_id:
        payload["model"] = payload["model"].replace(f"{prefix_id}.", "")

    return await send_post_request(
        url=f"{url}/api/chat",
        payload=json.dumps(payload),
        stream=form_data.stream,
        key=get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS),
        content_type="application/x-ndjson",
        user=user,
    )


# TODO: we should update this part once Ollama supports other types
class OpenAIChatMessageContent(BaseModel):
    type: str
    model_config = ConfigDict(extra="allow")


class OpenAIChatMessage(BaseModel):
    role: str
    content: Union[str, list[OpenAIChatMessageContent]]

    model_config = ConfigDict(extra="allow")


class OpenAIChatCompletionForm(BaseModel):
    model: str
    messages: list[OpenAIChatMessage]

    model_config = ConfigDict(extra="allow")


class OpenAICompletionForm(BaseModel):
    model: str
    prompt: str

    model_config = ConfigDict(extra="allow")


@router.post("/v1/completions")
@router.post("/v1/completions/{url_idx}")
async def generate_openai_completion(
    request: Request,
    form_data: dict,
    url_idx: Optional[int] = None,
    user=Depends(get_verified_user),
):
    try:
        form_data = OpenAICompletionForm(**form_data)
    except Exception as e:
        log.exception(e)
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

    payload = {**form_data.model_dump(exclude_none=True, exclude=["metadata"])}
    if "metadata" in payload:
        del payload["metadata"]

    model_id = form_data.model
    if ":" not in model_id:
        model_id = f"{model_id}:latest"

    model_info = Models.get_model_by_id(model_id)
    if model_info:
        if model_info.base_model_id:
            payload["model"] = model_info.base_model_id
        params = model_info.params.model_dump()

        if params:
            payload = apply_model_params_to_body_openai(params, payload)

        # Check if user has access to the model
        if user.role == "user":
            if not (
                user.id == model_info.user_id
                or has_access(
                    user.id, type="read", access_control=model_info.access_control
                )
            ):
                raise HTTPException(
                    status_code=403,
                    detail="Model not found",
                )
    else:
        if user.role != "admin":
            raise HTTPException(
                status_code=403,
                detail="Model not found",
            )

    if ":" not in payload["model"]:
        payload["model"] = f"{payload['model']}:latest"

    url, url_idx = await get_ollama_url(request, payload["model"], url_idx)
    api_config = request.app.state.config.OLLAMA_API_CONFIGS.get(
        str(url_idx),
        request.app.state.config.OLLAMA_API_CONFIGS.get(url, {}),  # Legacy support
    )

    prefix_id = api_config.get("prefix_id", None)

    if prefix_id:
        payload["model"] = payload["model"].replace(f"{prefix_id}.", "")

    return await send_post_request(
        url=f"{url}/v1/completions",
        payload=json.dumps(payload),
        stream=payload.get("stream", False),
        key=get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS),
        user=user,
    )


@router.post("/v1/chat/completions")
@router.post("/v1/chat/completions/{url_idx}")
async def generate_openai_chat_completion(
    request: Request,
    form_data: dict,
    url_idx: Optional[int] = None,
    user=Depends(get_verified_user),
):
    metadata = form_data.pop("metadata", None)

    try:
        completion_form = OpenAIChatCompletionForm(**form_data)
    except Exception as e:
        log.exception(e)
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

    payload = {**completion_form.model_dump(exclude_none=True, exclude=["metadata"])}
    if "metadata" in payload:
        del payload["metadata"]

    model_id = completion_form.model
    if ":" not in model_id:
        model_id = f"{model_id}:latest"

    model_info = Models.get_model_by_id(model_id)
    if model_info:
        if model_info.base_model_id:
            payload["model"] = model_info.base_model_id

        params = model_info.params.model_dump()

        if params:
            payload = apply_model_params_to_body_openai(params, payload)
            payload = apply_model_system_prompt_to_body(params, payload, metadata, user)

        # Check if user has access to the model
        if user.role == "user":
            if not (
                user.id == model_info.user_id
                or has_access(
                    user.id, type="read", access_control=model_info.access_control
                )
            ):
                raise HTTPException(
                    status_code=403,
                    detail="Model not found",
                )
    else:
        if user.role != "admin":
            raise HTTPException(
                status_code=403,
                detail="Model not found",
            )

    if ":" not in payload["model"]:
        payload["model"] = f"{payload['model']}:latest"

    url, url_idx = await get_ollama_url(request, payload["model"], url_idx)
    api_config = request.app.state.config.OLLAMA_API_CONFIGS.get(
        str(url_idx),
        request.app.state.config.OLLAMA_API_CONFIGS.get(url, {}),  # Legacy support
    )

    prefix_id = api_config.get("prefix_id", None)
    if prefix_id:
        payload["model"] = payload["model"].replace(f"{prefix_id}.", "")

    return await send_post_request(
        url=f"{url}/v1/chat/completions",
        payload=json.dumps(payload),
        stream=payload.get("stream", False),
        key=get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS),
        user=user,
    )


@router.get("/v1/models")
@router.get("/v1/models/{url_idx}")
async def get_openai_models(
    request: Request,
    url_idx: Optional[int] = None,
    user=Depends(get_verified_user),
):

    models = []
    if url_idx is None:
        model_list = await get_all_models(request, user=user)
        models = [
            {
                "id": model["model"],
                "object": "model",
                "created": int(time.time()),
                "owned_by": "openai",
            }
            for model in model_list["models"]
        ]

    else:
        url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
        try:
            r = requests.request(method="GET", url=f"{url}/api/tags")
            r.raise_for_status()

            model_list = r.json()

            models = [
                {
                    "id": model["model"],
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "openai",
                }
                for model in models["models"]
            ]
        except Exception as e:
            log.exception(e)
            error_detail = "Open WebUI: Server Connection Error"
            if r is not None:
                try:
                    res = r.json()
                    if "error" in res:
                        error_detail = f"Ollama: {res['error']}"
                except Exception:
                    error_detail = f"Ollama: {e}"

            raise HTTPException(
                status_code=r.status_code if r else 500,
                detail=error_detail,
            )

    if user.role == "user" and not BYPASS_MODEL_ACCESS_CONTROL:
        # Filter models based on user access control
        filtered_models = []
        for model in models:
            model_info = Models.get_model_by_id(model["id"])
            if model_info:
                if user.id == model_info.user_id or has_access(
                    user.id, type="read", access_control=model_info.access_control
                ):
                    filtered_models.append(model)
        models = filtered_models

    return {
        "data": models,
        "object": "list",
    }


class UrlForm(BaseModel):
    url: str


class UploadBlobForm(BaseModel):
    filename: str


def parse_huggingface_url(hf_url):
    try:
        # Parse the URL
        parsed_url = urlparse(hf_url)

        # Get the path and split it into components
        path_components = parsed_url.path.split("/")

        # Extract the desired output
        model_file = path_components[-1]

        return model_file
    except ValueError:
        return None


async def download_file_stream(
    ollama_url, file_url, file_path, file_name, chunk_size=1024 * 1024
):
    done = False

    if os.path.exists(file_path):
        current_size = os.path.getsize(file_path)
    else:
        current_size = 0

    headers = {"Range": f"bytes={current_size}-"} if current_size > 0 else {}

    timeout = aiohttp.ClientTimeout(total=600)  # Set the timeout

    async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
        async with session.get(file_url, headers=headers) as response:
            total_size = int(response.headers.get("content-length", 0)) + current_size

            with open(file_path, "ab+") as file:
                async for data in response.content.iter_chunked(chunk_size):
                    current_size += len(data)
                    file.write(data)

                    done = current_size == total_size
                    progress = round((current_size / total_size) * 100, 2)

                    yield f'data: {{"progress": {progress}, "completed": {current_size}, "total": {total_size}}}\n\n'

                if done:
                    file.seek(0)
                    hashed = calculate_sha256(file)
                    file.seek(0)

                    url = f"{ollama_url}/api/blobs/sha256:{hashed}"
                    response = requests.post(url, data=file)

                    if response.ok:
                        res = {
                            "done": done,
                            "blob": f"sha256:{hashed}",
                            "name": file_name,
                        }
                        os.remove(file_path)

                        yield f"data: {json.dumps(res)}\n\n"
                    else:
                        raise "Ollama: Could not create blob, Please try again."


# url = "https://huggingface.co/TheBloke/stablelm-zephyr-3b-GGUF/resolve/main/stablelm-zephyr-3b.Q2_K.gguf"
@router.post("/models/download")
@router.post("/models/download/{url_idx}")
async def download_model(
    request: Request,
    form_data: UrlForm,
    url_idx: Optional[int] = None,
    user=Depends(get_admin_user),
):
    allowed_hosts = ["https://huggingface.co/", "https://github.com/"]

    if not any(form_data.url.startswith(host) for host in allowed_hosts):
        raise HTTPException(
            status_code=400,
            detail="Invalid file_url. Only URLs from allowed hosts are permitted.",
        )

    if url_idx is None:
        url_idx = 0
    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]

    file_name = parse_huggingface_url(form_data.url)

    if file_name:
        file_path = f"{UPLOAD_DIR}/{file_name}"

        return StreamingResponse(
            download_file_stream(url, form_data.url, file_path, file_name),
        )
    else:
        return None


# TODO: Progress bar does not reflect size & duration of upload.
@router.post("/models/upload")
@router.post("/models/upload/{url_idx}")
async def upload_model(
    request: Request,
    file: UploadFile = File(...),
    url_idx: Optional[int] = None,
    user=Depends(get_admin_user),
):
    if url_idx is None:
        url_idx = 0
    ollama_url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    # --- P1: save file locally ---
    chunk_size = 1024 * 1024 * 2  # 2 MB chunks
    with open(file_path, "wb") as out_f:
        while True:
            chunk = file.file.read(chunk_size)
            # log.info(f"Chunk: {str(chunk)}") # DEBUG
            if not chunk:
                break
            out_f.write(chunk)

    async def file_process_stream():
        nonlocal ollama_url
        total_size = os.path.getsize(file_path)
        log.info(f"Total Model Size: {str(total_size)}")  # DEBUG

        # --- P2: SSE progress + calculate sha256 hash ---
        file_hash = calculate_sha256(file_path, chunk_size)
        log.info(f"Model Hash: {str(file_hash)}")  # DEBUG
        try:
            with open(file_path, "rb") as f:
                bytes_read = 0
                while chunk := f.read(chunk_size):
                    bytes_read += len(chunk)
                    progress = round(bytes_read / total_size * 100, 2)
                    data_msg = {
                        "progress": progress,
                        "total": total_size,
                        "completed": bytes_read,
                    }
                    yield f"data: {json.dumps(data_msg)}\n\n"

            # --- P3: Upload to ollama /api/blobs ---
            with open(file_path, "rb") as f:
                url = f"{ollama_url}/api/blobs/sha256:{file_hash}"
                response = requests.post(url, data=f)

            if response.ok:
                log.info(f"Uploaded to /api/blobs")  # DEBUG
                # Remove local file
                os.remove(file_path)

                # Create model in ollama
                model_name, ext = os.path.splitext(file.filename)
                log.info(f"Created Model: {model_name}")  # DEBUG

                create_payload = {
                    "model": model_name,
                    # Reference the file by its original name => the uploaded blob's digest
                    "files": {file.filename: f"sha256:{file_hash}"},
                }
                log.info(f"Model Payload: {create_payload}")  # DEBUG

                # Call ollama /api/create
                # https://github.com/ollama/ollama/blob/main/docs/api.md#create-a-model
                create_resp = requests.post(
                    url=f"{ollama_url}/api/create",
                    headers={"Content-Type": "application/json"},
                    data=json.dumps(create_payload),
                )

                if create_resp.ok:
                    log.info(f"API SUCCESS!")  # DEBUG
                    done_msg = {
                        "done": True,
                        "blob": f"sha256:{file_hash}",
                        "name": file.filename,
                        "model_created": model_name,
                    }
                    yield f"data: {json.dumps(done_msg)}\n\n"
                else:
                    raise Exception(
                        f"Failed to create model in Ollama. {create_resp.text}"
                    )

            else:
                raise Exception("Ollama: Could not create blob, Please try again.")

        except Exception as e:
            res = {"error": str(e)}
            yield f"data: {json.dumps(res)}\n\n"

    return StreamingResponse(file_process_stream(), media_type="text/event-stream")
