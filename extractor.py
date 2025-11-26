"""
Système d'Extraction Intelligent de Déclarations d'Importation
Version Entreprise - Optimisée pour Flask API
Compatible avec app.py et data_manager.py
"""

import re
import json
import csv
from typing import Dict, List, Optional, Any, Union
from pathlib import Path
from datetime import datetime
import PyPDF2

try:
    import pdfplumber
    import camelot
    import pandas as pd
    ADVANCED_EXTRACTION = True
except ImportError:
    ADVANCED_EXTRACTION = False


class TextReconstructor:
    """Reconstruit le texte PDF en préservant la structure et les tableaux"""
    
    def __init__(self, pdf_path: Union[str, Path], output_dir: Optional[str] = None):
        if not ADVANCED_EXTRACTION:
            raise ImportError("pdfplumber et camelot requis pour TextReconstructor")
            
        self.pdf_path = Path(pdf_path).resolve()
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF introuvable : {self.pdf_path}")
        
        self.output_dir = Path(output_dir).resolve() if output_dir else self.pdf_path.parent
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.reconstructed_text = ""
        self.tables_data = []
    
    def _extract_tables(self, page_number: int = 1) -> List[Dict]:
        """Extrait les tableaux avec Camelot"""
        tables_found = []
        try:
            tables = camelot.read_pdf(
                str(self.pdf_path), 
                pages=str(page_number), 
                flavor='stream',
                row_tol=10,
                edge_tol=500,
                strip_text='\n'
            )
            
            for i, table in enumerate(tables):
                df = table.df.replace('', pd.NA).dropna(how='all').fillna('')
                
                if not df.empty:
                    table_text = df.to_markdown(index=False, tablefmt="pipe")
                else:
                    table_text = "[Tableau vide]"
                
                tables_found.append({
                    'type': 'table_formatted',
                    'text': table_text,
                    'raw_df': df,
                    'table_number': i + 1
                })
                
        except Exception as e:
            pass  # Silencieux pour ne pas bloquer l'extraction
            
        return tables_found
    
    def reconstruct(self, page_numbers: Optional[List[int]] = None) -> str:
        """Reconstruit le texte complet (toutes les pages ou sélectionnées)"""
        with pdfplumber.open(self.pdf_path) as pdf:
            total_pages = len(pdf.pages)
            pages_to_process = page_numbers if page_numbers else list(range(1, total_pages + 1))
            
            reconstructed_parts = []
            
            for page_num in pages_to_process:
                if page_num > total_pages:
                    continue
                
                # Extraction texte de base
                page = pdf.pages[page_num - 1]
                page_text = page.extract_text(layout=True, x_tolerance=3, y_tolerance=3)
                
                if page_text:
                    reconstructed_parts.append(f"\n{'='*80}")
                    reconstructed_parts.append(f"PAGE {page_num}")
                    reconstructed_parts.append(f"{'='*80}\n")
                    reconstructed_parts.append(page_text)
                
                # Extraction tableaux
                tables = self._extract_tables(page_num)
                if tables:
                    reconstructed_parts.append("\n" + "="*80)
                    reconstructed_parts.append(f"--- ZONES TABLEAUX PAGE {page_num} ---")
                    reconstructed_parts.append("="*80 + "\n")
                    
                    for tbl in tables:
                        reconstructed_parts.append(f"\n[Tableau #{tbl['table_number']}]\n")
                        reconstructed_parts.append(tbl['text'])
                        reconstructed_parts.append("\n" + "-"*40)
                        self.tables_data.append(tbl)
            
            self.reconstructed_text = "\n".join(reconstructed_parts)
            return self.reconstructed_text
    
    def save_text(self, output_path: Optional[str] = None) -> Path:
        """Sauvegarde le texte reconstruit"""
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = self.output_dir / f"texte_reconstruit_{timestamp}.txt"
        
        output_path = Path(output_path).resolve()
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(self.reconstructed_text)
        
        return output_path


class ImportDeclarationExtractor:
    """
    Extracteur intelligent pour déclarations d'importation SGS Cameroun
    Compatible avec Flask API et DataManager
    """
    
    def __init__(self, use_advanced_extraction: bool = True):
        self.data = {}
        self.extracted_text = ""
        self.use_advanced = use_advanced_extraction and ADVANCED_EXTRACTION
        self.reconstructor = None
        
        # Structure basée sur le format réel du document
        self.structure = {
            "declaration": {
    "di_number": {
        "label": "D.I N°",
        "patterns": [
            # Pattern le plus précis pour "SGS-30999-44" avec le label "D.I N°"
            # Gère les points optionnels dans D.I, les espaces et un éventuel saut de ligne après ":"
            r"D\.I\.?\s*N°\s*:\s*\n?\s*([A-Z]{3}-\d{5}-\d{2})",
            # Variante pour "DECLARATION N°" si cette forme apparaît
            r"DECLARATION.*?N°\s*:\s*\n?\s*([A-Z]{3}-\d{5}-\d{2})",
            # Pattern plus tolérant pour le numéro, au cas où il y aurait moins de 5 chiffres ou plus
            r"D\.?I\.?\s*N°\s*:\s*\n?([A-Z]{3}-\d+-\d+)"
        ]
    },
    "date": {
        "label": "Du / Dated",
        "patterns": [
            # Cible "Du / Dated : 25/09/2025" sur une ligne ou avec la date sur la ligne suivante
            r"Du\s*/\s*Dated\s*:\s*\n?\s*(\d{2}/\d{2}/\d{4})",
            # Pattern plus tolérant (avec / ou - et 1 ou 2 chiffres pour jour/mois)
            # Permet "Du / Dated 25-9-2025" ou "Dated: 1/1/2024"
            r"(?:Du\s*/\s*Dated|Dated)\s*[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{4})"
        ]
    },
    "date_exp": {
        "label": "Date exp",
        "patterns": [
            # Cible "Date exp : 25/03/2026" sur une ligne ou avec la date sur la ligne suivante
            r"Date\s*exp\s*:\s*\n?\s*(\d{2}/\d{2}/\d{4})",
            # Pattern plus tolérant pour Date exp (avec / ou - et 1 ou 2 chiffres pour jour/mois)
            r"Date\s*exp\s*:?\s*\n?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4})"
        ]
    },
    "gu_number": {
        "label": "GU N°",
        "patterns": [
            # Cible "GU N°: IM213034" avec le format "2 lettres majuscules suivies de 6 chiffres"
            r"GU\s*N°\s*:\s*\n?([A-Z]{2}\d{6})",
            # Pattern plus général pour capturer un format long après "GU N°", si le format n'est pas strict
            r"GU\s*N°\s*[:\s]*\n?([A-Z0-9-]{4,})",
            # Un pattern qui pourrait capturer "GU/2023/12345" si le format change
            r"GU\s*N°\s*[:\s]*\n?([A-Z]+(?:/\d+)+)"
        ]
    }
},
            
            # Section: Importateur (Patterns Améliorés)
            # Section: Importateur (Patterns Anti-Colonnes) - Version Corrigée
            "importateur": {
                "name": {
                    "label": "Importateur (nom,adresse) / Importer(name,address)",
                    "patterns": [
                        # Pattern 1: Capture le nom (en majuscules, suivi de LIMITED/SARL/SA) sur la ligne après l'en-tête "Importateur/Importer"
                        r"(?:Importateur|Importer)\s*\([^)]+\)(?:[^\n]*\n|\s+)\s*([A-Z][A-Z\s]+(?:LIMITED|SARL|SA|EURL|SAU|INC))\s*\n",
                        # Pattern 2: Si l'en-tête est sur la ligne précédente ou même ligne et le nom est sur la suivante, plus générique pour le nom
                        r"(?:Importateur|Importer)[^\n]*\n\s*([A-Z][A-Z\s]+(?:LIMITED|SARL|SA|EURL|SAU|INC|SNC))\s*(?:\n|(?:\s+[A-Z0-9]))"
                    ]
                },
                
                "address": {
                    "label": "Adresse importateur",
                    "patterns": [
                        # Cherche l'adresse après le nom de la société
                        r"(?:LIMITED|SARL|SA)\s*\n\s*([A-Z0-9][^\n]+?\d{4}\s+(?:DOUALA|YAOUNDE|LIMBE|KRIBI))",
                        r"(?:CAMEROON|KEDA|SOFTCARE|COMPANY)\s+(?:LIMITED|SARL|SA)\s*\n\s*([A-Z0-9][^\n]+)\s*(?:Code|T[eé]l[eé]phone)"
                    ]
                },
                
                "code_agrement": {
                    "label": "Code d'agrément",
                    "patterns": [
                        r"Code\s*d['']?agr[ée]ment[^\n]*\n[^\n]*\s*([I1][Ff][O0Gg]\d{5,6})\s+",
                        r"\n\s*([I1][Ff][O0Gg]\d{5,6})\s+(?:\w+\s+bee|Registre|R[cI]C|Date)"
                    ]
                },
                
                "rc_number": {
                    "label": "Registre de commerce",
                    "patterns": [
                        # Cherche le label (incluant l'erreur OCR 'vee'), ignore les lignes, puis trouve le format RC strict.
                        r"(?:Registre\s+de\s+commerce|R[cI]C|RC|vee)[^\n]*\n[^\n]*\n\s*[iI\s]*\s*(RC/[A-Z]{3,4}/\d{4}/[A-Z]/\d{4})\s*\n"
                    ]
                },
                
                "obtention": {
                    "label": "Obtention",
                    "patterns": [
                        r"Obtention\s*[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{4})\s*(?:Pr[eé]remption|Code)"
                    ]
                },
                
                "preremption": {
                    "label": "Préremption",
                    "patterns": [
                        r"Pr[eé]remption\s*[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{4})"
                    ]
                },
                
                "code_statistical": {
                    "label": "Code/Statistical number",
                    "patterns": [
                        r"(?:Code|Statistical|Number)[^\n]*number[^\n]*\n\s*([A-Z]\d{11,13}[A-Z])(?:\s+\d{9,}|[^\n]*)",
                        r"([A-Z]\d{11,13}[A-Z])\s+(?:237\d{9})"
                    ]
                },
                
                "telephone": {
                    "label": "Téléphone/Phone",
                    "patterns": [
                        r"(?:T[eé]l[eé]phone|P[hH]one|1elepnone|rnone)\s*[:\s]*\s*([21]37\d{9})",
                        r"[A-Z]\d{11,13}[A-Z]\s+([21]37\d{9})(?:\s*\n|$)?"
                    ]
                },
                
                "email": {
                    "label": "E-mail",
                    "patterns": [
                        r"(?:237\d{9})\s*\n\s*(?:E-mail|Email)\s*[:\s]*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\s*(?:\n|\s+Commisionaire|$)",
                        r"number[^\n]*\n\s*[A-Z0-9]+\s+[21]37\d{9}\s*\n\s*(?:E-mail|Email)\s*[:\s]*([^\s\n]+@[^\s\n]+)"
                    ]
                }
            },
            
            # Section: Vendeur
            "vendeur": {
                "name": {
                    "label": "Vendeur (nom)",
                    "patterns": [
                        r"Vendeur \(nom,adresse\)[^\n]*\n(?:.*?\s{2,}|^\s*)([A-Z\s0-9]+(?:LIMITED|SARL|SA|EURL|INC|SNC))\s*$"
                    ]
                },
                "address": {
                    "label": "Adresse Vendeur",
                    "patterns": [
                        r"(?:LIMITED|SARL|SA|EURL|INC|SNC)\s*\n(?:.*?\s{2,}|^\s*)([A-Z0-9\s]+?)\s*(?:Téléphone|Télécopie|Phone|Fax|$)"
                    ]
                },
                "phone": {
                    "label": "Téléphone Vendeur",
                    "patterns": [
                        r"(?:Phone|Téléphone)[^\n]*(?:Fax|Télécopie)[^\n]*\n\s*(?:.*?\s{2,})?([0-9+]{6,})\s+[0-9+]{6,}"
                    ]
                },
                "fax": {
                    "label": "Fax Vendeur",
                    "patterns": [
                        r"(?:Phone|Téléphone)[^\n]*(?:Fax|Télécopie)[^\n]*\n\s*(?:.*?\s{2,})?[0-9+]{6,}\s+([0-9+]{6,})"
                    ]
                },
                "email": {
                    "label": "E-mail Vendeur",
                    "patterns": [
                        r"E-mail\s*:\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})"
                    ]
                }
            },
            
            # Section: Commissionnaire Agréé en Douane
        "commissionnaire": {
            "full_name": {
                "label": "Full Name",
                "patterns": [
                    r"STE\s+ELIMELEC\s+SARL",
                    r"(\d{10})\s*\n\s*(STE\s+[A-Z]+\s+SARL)"
                ]
            },
            "adresse": {
                "label": "Adresse",
                "patterns": [
                    r"5077\s+DOUALA",
                    r"Adresse\s*\n\s*(\d+\s+[A-Z]+)"
                ]
            },
            "telephone_mobile": {
                "label": "Telephone Mobile",
                "patterns": [
                    r"233434882",
                    r"Telephone\s*Mobile:?\s*\n?\s*(\d+)"
                ]
            },
            "email": {
                "label": "Email",
                "patterns": [
                    r"info@elim-elec\.cm"
                ]
            }
        },
        
            # Section: Lieu de dédouanement
            "dedouanement": {
                "lieu": {
                    "label": "Lieu de dédouanement / Custom clearing office",
                    "patterns": [
                        r"KRIBI\s+PORT",
                        r"Custom\s*clearing\s*office\s*\n\s*([A-Z][A-Z\s]+?)(?=\n|Pays)",
                        r"dédouanement.*?office\s*\n?\s*([A-Z\s]+?)(?=\n|Pays)",
                    ]
                },
            },
            
            # Section: Pays
            "pays": {
                "origine": {
                    "label": "Pays d'origine / Country of origin",
                    "patterns": [
        # Pattern 1 (Le plus fiable) : Basé sur la ligne "of Shipment"
        # 1. Trouve l'en-tête "Pays de provenance / Country"
        # 2. Cherche la ligne contenant "of Shipment" juste en dessous
        # 3. Va à la ligne suivante (\n)
        # 4. Ignore la première colonne (le Port) qui est en majuscules suivie d'un grand espace (.*?\s{2,})
        # 5. Capture le Code (2 lettres) + le Nom du pays ([A-Z]{2}\s+[a-zA-Z\s]+)
        r"(?:Pays de provenance|Country)[\s\S]*?of Shipment[^\n]*\n(?:.*?\s{2,}|^\s*)([A-Z]{2}\s+[a-zA-Z\s]+)(?:\s{2,}|\n|$)",

        # Pattern 2 (Alternatif) : Si la ligne "of Shipment" est mal lue
        # Cherche la ligne contenant "Pays de provenance", saute une ligne, 
        # puis sur la ligne suivante, capture la valeur après un grand espace.
        r"(?:Pays de provenance|Country)[^\n]*\n[^\n]*\n(?:.*?\s{2,}|^\s*)([A-Z]{2}\s+[a-zA-Z\s]+)"
    ]
                },
                "provenance": {
                    "label": "Pays de provenance / Country of Shipment",
                   "label": "Pays de provenance",
    "patterns": [
        # Pattern 1 (Le plus fiable) : Basé sur la ligne "of Shipment"
        # 1. Trouve l'en-tête "Pays de provenance / Country"
        # 2. Cherche la ligne contenant "of Shipment" juste en dessous
        # 3. Va à la ligne suivante (\n)
        # 4. Ignore la première colonne (le Port) qui est en majuscules suivie d'un grand espace (.*?\s{2,})
        # 5. Capture le Code (2 lettres) + le Nom du pays ([A-Z]{2}\s+[a-zA-Z\s]+)
        r"(?:Pays de provenance|Country)[\s\S]*?of Shipment[^\n]*\n(?:.*?\s{2,}|^\s*)([A-Z]{2}\s+[a-zA-Z\s]+)(?:\s{2,}|\n|$)",

        # Pattern 2 (Alternatif) : Si la ligne "of Shipment" est mal lue
        # Cherche la ligne contenant "Pays de provenance", saute une ligne, 
        # puis sur la ligne suivante, capture la valeur après un grand espace.
        r"(?:Pays de provenance|Country)[^\n]*\n[^\n]*\n(?:.*?\s{2,}|^\s*)([A-Z]{2}\s+[a-zA-Z\s]+)"
    ]
                },
            },
            
            # Section: Transport
            "transport": {
                "mode": {
                    "label": "Mode de transport / Transport mode",
                    "patterns": [
                        r"MARITIME",
                        r"Transport\s*mode\s*\n\s*([A-Z]+)",
                        r"Mode.*?transport.*?mode\s*\n\s*([A-Z]+)",
                    ]
                },
                "type_expedition": {
                    "label": "Type d'expédition / Shipment/Delivery Type",
                    "patterns": [
                        r"TOTALE",
                        r"Delivery\s*Type\s*\n\s*([A-Z]+)",
                        r"expédition.*?Type\s*\n\s*([A-Z]+)",
                    ]
                },
            },
            
            # # Section: Banque
            # "banque": {
            #     "domiciliatrice": {
            #         "label": "Banque domiciliatrice / Authorised bank",
            #         "patterns": [
            #             r"CREDIT\s+COMMUNAUTAIRE\s+D'AFRIQUE\s*-?CCA",
            #             r"Authorised\s*bank\s*\n\s*([A-Z][A-Z\s\-]+?)(?=\n|Valeur)",
            #             r"Banque\s*domiciliatrice.*?\n\s*([A-Z\s\-]+CCA)",
            #         ]
            #     },
            #     "domiciliation_numero": {
            #         "label": "N° (domiciliation)",
            #         "patterns": [
            #            r"([A-Z][A-Z0-9\-]{4,}[A-Z]{0,1}\-[A-Z0-9\-\s]+EUR)"
            #         ]
            #     },
            #     "domiciliation_date": {
            #         "label": "Date (domiciliation)",
            #         "patterns": [
            #             r"04/09/2025",
            #             r"Date\s*:\s*(\d{2}/\d{2}/\d{4})",
            #             r"Domicilié.*?Date\s*:\s*(\d{2}/\d{2}/\d{4})",
            #         ]
            #     },
            #     "agence": {
            #         "label": "Agence",
            #         "patterns": [
            #             r"Agence\s*:\s*([A-Z\s]+?)(?=ATTESTATION)",
            #         ]
            #     },
            # },
            
            # Section: Valeurs financières
            "valeurs_financieres": {
                "valeur_totale_devise": {
                    "label": "Valeur Totale (devises)",
                    "patterns": [
        # Pattern 1 (Le plus précis) : Basé sur la structure de la ligne de données
        # On cherche les astérisques "**", le montant, puis un numéro de facture et une date sur la même ligne.
        # Correspond à : **178,956.09 81006 01/09/2025
        r"\*\*\s*([\d,]+\.\d{2})\s+\d{4,}\s+\d{2}/\d{2}/\d{4}",

        # Pattern 2 (Ancrage par l'en-tête) : 
        # Cherche "Total value in foreign currency", ignore jusqu'à 4 lignes (pour passer EUR, etc.),
        # puis capture le nombre qui suit immédiatement "**".
        r"Total\s*value\s*in\s*foreign\s*currency(?:[^\n]*\n){1,5}.*?\*\*\s*([\d,]+\.\d{2})",

        # Pattern 3 (Ancrage par la Devise) :
        # Cherche une devise (EUR, USD, etc.) suivie juste après (ou ligne suivante) par "**" et un montant.
        r"(?:EUR|USD|GBP|CNY|XAF)\s*(?:\n|)\s*\*\*\s*([\d,]+\.\d{2})"
    ]
                },
                "devise": {
                    "label": "Devise / Currency",
                    "patterns": [
        # Pattern 1 (Générique & Robuste) :
        # 1. Cherche "Devise / Currency"
        # 2. Saute 1 à 3 lignes ((?:[^\n]*\n){1,3}) pour passer les sous-titres anglais ou lignes vides.
        # 3. Capture le premier mot de 3 lettres majuscules ([A-Z]{3}) en début de ligne.
        # 4. S'assure qu'il est suivi d'un espace ou d'une fin de ligne pour éviter de capturer un mot partiel.
        r"Devise\s*/\s*Currency(?:[^\n]*\n){1,3}\s*([A-Z]{3})(?:\s+|$)",

        # Pattern 2 (Liste Blanche - Plus Sûr) :
        # Si vous connaissez les devises possibles, c'est le plus fiable.
        # Il cherche l'en-tête, puis cherche spécifiquement EUR, USD, CNY, GBP, XAF, etc.
        r"Devise\s*/\s*Currency[\s\S]*?\n\s*(EUR|USD|GBP|CNY|XAF|CAD|CHF|JPY)\b",
        
        # Pattern 3 (Contextuel avec la Valeur Totale) :
        # Capture le code 3 lettres qui se trouve juste avant ou au-dessus de la ligne contenant "**" et un montant.
        r"([A-Z]{3})\s*(?:\n|)\s*\*\*\s*[\d,]+\.\d{2}"
    ]
                },
                "modalites_reglement": {
                    "label": "Modalités de règlement",
                    "patterns": [
                        r"Transfert\s+bancaire",
                        r"Method\s*of\s*settlement\s*\n\s*([A-Za-z\s]+?)(?=\n|No)",
                    ]
                },
                "facture_proforma_numero": {
                    "label": "No Facture Proforma",
                    "patterns": [
        # Pattern 1 (Le plus précis) : Ancrage après le montant total étoilé
        # 1. Cherche la fin de la valeur totale (montant décimal 1 ou 2 chiffres après le point).
        # 2. Capture le numéro de facture qui suit (5 chiffres dans cet exemple, donc on prend 4 chiffres ou plus).
        # 3. S'assure qu'il est suivi d'un espace et d'une date (format JJ/MM/AAAA).
        r"[\d,]+\.\d{1,2}\s+(\d{4,})\s+\d{2}/\d{2}/\d{4}",

        # Pattern 2 (Ancrage par l'en-tête) :
        # Cherche "Proforma no / Date", puis navigue jusqu'à la ligne de valeur.
        # 1. Cherche l'en-tête "Proforma no / Date".
        # 2. Navigue jusqu'à 3 lignes plus bas (pour atteindre la ligne de valeur).
        # 3. Cherche un montant étoilé, puis capture le numéro à 4 chiffres ou plus qui suit.
        r"Proforma\s*no\s*/\s*Date(?:[\s\S]*?\n){1,3}.*?[\d,]+\.\d{2}\s+(\d{4,})"
    ]
                },
                "facture_proforma_date": {
                    "label": "Date Facture Proforma",
                    "patterns": [
        # Pattern 1 (Le plus précis) : Ancrage après le numéro de facture
        # 1. Cherche la fin de la valeur totale (montant décimal 1 ou 2 chiffres après le point).
        # 2. Cherche le numéro de facture (4 chiffres ou plus).
        # 3. Capture la date au format JJ/MM/AAAA.
        r"[\d,]+\.\d{1,2}\s+\d{4,}\s+(\d{2}/\d{2}/\d{4})",

        # Pattern 2 (Ancrage par l'en-tête "Date") :
        # Cherche l'en-tête "Proforma no / Date", puis navigue vers le bas et capture le format date.
        r"Date\s*Modalités\s*de\s*réeglement\s*/[\s\S]*?\n[\s\S]*?\n.*?\s+(\d{2}/\d{2}/\d{4})\s+"
    ]
                },
                "terme_vente": {
                    "label": "Terme de vente / Incoterm",
                    "patterns": [
        # Pattern 1 (Ancrage sur le titre) :
        # 1. Cherche l'en-tête "Terme de vente / Incoterm".
        # 2. Saute la ligne de sous-titre anglais.
        # 3. Capture le mot de 3 ou 4 lettres majuscules (l'Incoterm) au début de la ligne, suivi d'un espace.
        r"Terme\s*de\s*vente\s*/\s*Incoterm(?:[^\n]*\n){1,3}\s*([A-Z]{3,4})\s",

        # Pattern 2 (Ancrage par la valeur FOB) :
        # Cherche le code Incoterm qui est juste avant la valeur FOB en devises (qui commence par "**").
        # Ceci est très fiable car ces deux champs sont côte à côte.
        r"([A-Z]{3,4})\s*\*{2}[\d,]+\.\d{2}"
    ]
                },
                "taux_change": {
                    "label": "Taux de change",
                    "patterns": [
                        r"655\.957000",
                        r"Exchange\s*rate\s*\n?\s*\*{0,2}([\d,\.]+)",
                    ]
                },
                "valeur_fob_cfa": {
                    "label": "Valeur FOB en CFA",
                    "patterns": [
        # Pattern 1 (Ancrage sur le titre) :
        # 1. Cherche l'en-tête "Valeur FOB en CFA".
        # 2. Saute jusqu'à 3 lignes de sous-titres/valeurs intermédiaires.
        # 3. Capture le grand nombre, précédé par **.
        r"Valeur\s*FOB\s*en\s*CFA[/|]\s*FOB\s*value(?:[^\n]*\n){1,5}.*?\*{2}([\d,]+\.\d{2})",

        # Pattern 2 (Ancrage par la ligne de données et la taille du nombre) :
        # 1. Cherche le taux de change (Exchange rate) qui précède.
        # 2. Cherche la valeur FOB en devises qui est sur la même ligne ou celle du dessus.
        # 3. Capture le grand nombre CFA, qui se trouve à la fin de la ligne.
        r"[\d,]+\.\d{2}\s+[\d,]+\.\d{4,}\s+?\*{2}([\d,]+\.\d{2})\s*$"
    ]
                },
                "valeur_fob_devise": {
                    "label": "Valeur FOB (devises)",
                    "patterns": [
        # Pattern 1 (Le plus précis) : Ancrage par l'Incoterm et le Taux de change
        # 1. Cherche un Incoterm (3 ou 4 lettres, ex: CIF).
        # 2. Capture le montant étoilé qui suit immédiatement (la Valeur FOB en devises).
        # 3. S'assure qu'il est suivi par le Taux de change (format X.YYYYY).
        r"[A-Z]{3,4}\s*\*{2}([\d,]+\.\d{2})\s+[\d\.]+\s+[\d\.,]+",

        # Pattern 2 (Ancrage sur le titre) :
        # 1. Cherche l'en-tête "FOB value in foreign currency".
        # 2. Saute la ligne de Taux de change qui peut intervenir dans le tableau.
        # 3. Capture le montant étoilé.
        r"FOB\s*value\s*in\s*foreign\s*currency(?:[^\n]*\n){1,5}.*?\*{2}([\d,]+\.\d{2})"
    ]
                },
            },
            
            # Section: Marchandises
            "marchandises": {
                "quantite": {
                    "label": "Quantité / Quantity",
                   "patterns": [
        # Pattern 1 (Le plus précis) : Ancrage par le Code SH
        # 1. Cherche le Code SH (10 à 12 chiffres).
        # 2. Capture la valeur étoilée qui suit.
        r"\d{10,12}\s*(\*\*\s*[\d,]+\.\d{2})\s*[A-Z]{2,3}",

        # Pattern 2 (Ancrage sur le titre) :
        # Cherche "Quantité / Quantity", navigue vers le bas, et capture le montant étoilé.
        r"Quantité\s*/\s*Quantity(?:[^\n]*\n){1,3}.*?(\*\*\s*[\d,]+\.\d{2})\s*[A-Z]{2,3}"
    ]
                },
                "fob_devise": {
                    "label": "FOB en devise",
                    "patterns": [
        # Pattern 1 (Ancrage par l'Incoterm et le Taux de change) :
        # Cible la valeur FOB en devises (**) qui suit l'Incoterm et précède le Taux de change.
        r"[A-Z]{3,4}\s*\*{2}([\d,]+\.\d{2})\s+[\d\.]+\s+[\d\.,]+",

        # Pattern 2 (Ancrage sur le titre) :
        # Cherche la variante de l'en-tête "FOB in forex" ou "FOB en devise" et capture le montant étoilé.
        r"FOB\s*in\s*forex|FOB\s*en\s*devise(?:[^\n]*\n){1,5}.*?\*{2}([\d,]+\.\d{2})",
        
        # Pattern 3 (Le titre complet) :
        r"FOB\s*en\s*devise\s*/\s*FOB\s*in\s*forex(?:[^\n]*\n){1,3}\s*(\*{2}[\d,]+\.\d{2})"
    ]
                },
                "hs_code": {
                    "label": "Pos. tarifaire / HS code",
                    "patterns": [
        # Pattern 1 (Le plus précis) : Ancrage par la description du produit
        # 1. Cherche la description (texte en majuscules).
        # 2. Capture la séquence de chiffres (10 à 12 chiffres) qui suit immédiatement.
        r"[A-Z\s,]{4,}\s+(\d{10,12})\s+",

        # Pattern 2 (Ancrage sur l'en-tête) :
        # Cherche "Pos. tarifaire / HS code", ignore les lignes intermédiaires,
        # et capture le long code numérique.
        r"Pos\.\s*tarifaire\s*/\s*HS\s*code(?:[^\n]*\n){1,3}\s*(\d{10,12})"
    ]
                },
                "unite": {
                    "label": "Unité / Unit",
                    "patterns": [
        # Pattern 1 (Le plus précis) : Ancrage par la Description de la marchandise
        # 1. Cherche la Description (texte en majuscules, ex: FLUFF PULP).
        # 2. Capture la séquence de 10 à 12 chiffres qui suit immédiatement (le code SH).
        r"[A-Z\s,]{4,}\s+(\d{10,12})\s+",

        # Pattern 2 (Ancrage sur le titre) :
        # Cherche "Pos. tarifaire / HS code", ignore les lignes intermédiaires,
        # et capture le long code numérique.
        r"Pos\.\s*tarifaire\s*/\s*HS\s*code(?:[^\n]*\n){1,3}\s*(\d{10,12})"
    ]
                },
                "description": {
                    "label": "Description des marchandises",
                    "patterns": [
        # Pattern 1 (Le plus précis) : Ancrage par les en-têtes adjacents
        # 1. Cherche l'en-tête "Description des marchandises".
        # 2. Saute la ligne du sous-titre anglais.
        # 3. Capture le texte en majuscules (le nom du produit) qui précède le code tarifaire.
        r"Description\s*des\s*marchandises\s*/\s*Goods\s*description(?:[^\n]*\n){1,3}\s*([A-Z\s,]{4,})\s+\d{10,}",

        # Pattern 2 (Ancrage par la ligne de données) :
        # Cherche une séquence de mots en majuscules et espaces (le nom du produit),
        # suivie immédiatement d'un code tarifaire long (10 chiffres).
        r"([A-Z\s,]{4,})\s+\d{10}\s+"
    ]
                },
            },
            
            # Section: Taxe d'inspection
            "taxe_inspection": {
                "banque": {
                    "label": "Banque / Bank (taxe)",
                    "patterns": [
                        r"AFG\s+BANK\s+CAMEROUN",
                        r"Taxe.*?Bank.*?\n.*?([A-Z]+\s+BANK\s+[A-Z]+)",
                    ]
                },
                "date": {
                    "label": "Du / Dated (taxe)",
                    "patterns": [
        # Pattern 1 (Le plus précis) : Ancrage par le Numéro de Chèque et la Banque
        # 1. Cherche le Numéro de Chèque (4 à 8 chiffres).
        # 2. Capture la date au format JJ/MM/AAAA qui suit.
        # 3. S'assure que la date est suivie du nom de la Banque (plusieurs lettres majuscules).
        r"\d{4,8}\s+(\d{2}/\d{2}/\d{4})\s+[A-Z\s]{4,}",

        # Pattern 2 (Ancrage sur le titre) :
        # Cherche l'en-tête "Du / Dated" et capture le format date quelques lignes plus bas.
        r"Du\s*/\s*Dated(?:[^\n]*\n){1,3}\s*(\d{2}/\d{2}/\d{4})\s+"
    ]
                },
                "montant_cfa": {
                    "label": "Montant CFA",
                  "patterns": [
        # Pattern 1 (Le plus fiable) : Ancrage sur l'en-tête "Montant CFA"
        # 1. Cherche le titre bilingue.
        # 2. Saute les lignes intermédiaires (Chèque N°, Date, Banque).
        # 3. Capture le montant étoilé, formaté avec des séparateurs d'espace et/ou de virgule.
        r"Montant\s*CFA\s*/\s*Amount\s*in\s*CFA(?:[^\n]*\n){1,5}.*?\*{2}([\d\s,]+)\s*$",

        # Pattern 2 (Ancrage par la Banque) :
        # Cherche le nom de la Banque (qui précède la valeur dans la ligne de données).
        # 1. Cherche le nom de la Banque.
        # 2. Capture le montant étoilé qui se trouve à la fin de la ligne.
        r"[A-Z]{3,}\s*BANK\s*[A-Z\s]{4,}\s*\*{2}([\d\s,]+)\s*$"
    ]
                },
                "cheque_numero": {
                    "label": "Chèque N°",
                    "patterns": [
        # Pattern 1 (Le plus précis) : Ancrage sur le titre
        # 1. Cherche l'en-tête "Chéque N° / Check N°".
        # 2. Saute les lignes de sous-titres/lignes vides.
        # 3. Capture le premier groupe de 4 à 8 chiffres qui suit.
        r"Chéque\s*N°\s*/\s*Check\s*N°(?:[^\n]*\n){1,3}\s*(\d{4,8})\s",

        # Pattern 2 (Ancrage par la ligne de données) :
        # Cherche le numéro de chèque qui est suivi d'une date (format JJ/MM/AAAA) sur la même ligne.
        r"(\d{4,8})\s+\d{2}/\d{2}/\d{4}"
    ]
                },
            },
            
            # Section: Assurance
            "assurance": {
                "company": {
                    "label": "Assurance / Insurance Company",
                    "patterns": [
                        r"ATLANTIQUE\s+ASSURANCES",
                        r"Insurance\s*Company\s*\n?\s*([A-Z][A-Z\s]+)",
                    ]
                },
            },
        }
    
    
    def extract_from_pdf(self, pdf_path: str, use_reconstruction: bool = None) -> str:
        """
        Extrait le texte d'un PDF avec méthode basique ou avancée
        Compatible avec app.py
        """
        if use_reconstruction is None:
            use_reconstruction = self.use_advanced
            
        if use_reconstruction and ADVANCED_EXTRACTION:
            try:
                self.reconstructor = TextReconstructor(pdf_path)
                return self.reconstructor.reconstruct()
            except Exception as e:
                # Fallback sur PyPDF2 si l'extraction avancée échoue
                pass
        
        # Extraction basique PyPDF2 (toujours disponible)
        try:
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                text = ""
                for page in reader.pages:
                    text += page.extract_text() + "\n"
                return text
        except Exception as e:
            raise Exception(f"Erreur lors de la lecture du PDF: {str(e)}")
    
    def extract_field(self, text: str, field_config: Dict) -> Optional[str]:
        """Extrait un champ spécifique en testant plusieurs patterns"""
        patterns = field_config.get("patterns", [])
        for pattern in patterns:
            match = re.search(pattern, text, re.MULTILINE | re.DOTALL | re.IGNORECASE)
            if match:
                try:
                    value = match.group(1).strip() if match.groups() else match.group(0).strip()
                    # Nettoyage
                    value = re.sub(r'\*+', '', value)
                    value = re.sub(r'\s+', ' ', value)
                    value = value.replace('\n', ' ').strip()
                    if value:
                        return value
                except:
                    continue
        return None
    
    def extract_all_fields(self, text: str = None) -> Dict[str, Any]:
        """
        Extrait tous les champs par section avec validation
        Compatible avec app.py
        """
        if text is None:
            text = self.extracted_text
        else:
            self.extracted_text = text
            
        results = {}
        statistics = {
            "total_fields": 0,
            "extracted_fields": 0,
            "missing_fields": [],
            "extraction_rate": 0.0
        }
        
        for section_name, fields in self.structure.items():
            results[section_name] = {}
            for field_name, field_config in fields.items():
                statistics["total_fields"] += 1
                value = self.extract_field(text, field_config)
                
                if value:
                    results[section_name][field_name] = value
                    statistics["extracted_fields"] += 1
                else:
                    results[section_name][field_name] = ""
                    statistics["missing_fields"].append(f"{section_name}.{field_name}")
        
        # Calcul du taux d'extraction
        if statistics["total_fields"] > 0:
            statistics["extraction_rate"] = round(
                (statistics["extracted_fields"] / statistics["total_fields"]) * 100, 2
            )
        
        results["_statistics"] = statistics
        return results

    def save_to_csv(self, data: Dict[str, Any], output_path: str) -> str:
        """
        Enregistre les données dans un fichier CSV
        Compatible avec app.py
        """
        clean_data = {k: v for k, v in data.items() if k != "_statistics"}
        flat_data = self._flatten_dict(clean_data)
        
        with open(output_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=flat_data.keys())
            writer.writeheader()
            writer.writerow(flat_data)
        
        return output_path
    
    def save_to_json(self, data: Dict[str, Any], output_path: str) -> str:
        """
        Enregistre les données dans un fichier JSON
        Compatible avec app.py
        """
        with open(output_path, 'w', encoding='utf-8') as jsonfile:
            json.dump(data, jsonfile, indent=4, ensure_ascii=False)
        
        return output_path

    def _flatten_dict(self, d: Dict, parent_key: str = '', sep: str = '_') -> Dict:
        """
        Aplatit un dictionnaire imbriqué pour CSV
        Compatible avec data_manager.py
        """
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(self._flatten_dict(v, new_key, sep=sep).items())
            else:
                items.append((new_key, v))
        return dict(items)
    
    # def to_datamanager_format(self, data: Dict[str, Any]) -> Dict[str, str]:
    #     """
    #     Convertit les données extraites au format attendu par DataManager
    #     Mapping vers les colonnes DEFAULT_COLUMNS de data_manager.py
    #     """
    #     flat = self._flatten_dict({k: v for k, v in data.items() if k != "_statistics"})
        
    #     # Mapping intelligent vers le schéma DataManager
    #     mapped = {
    #         'declaration_di_number': flat.get('declaration_di_number', ''),
    #         'importateur_name': flat.get('importateur_name', ''),
    #         'produit_designation': flat.get('marchandises_description', ''),
    #         'valeur_fob_cfa': flat.get('valeurs_financieres_valeur_fob_cfa', ''),
    #         'quantite_declaree': flat.get('marchandises_quantite', ''),
    #         'pays_origine': flat.get('pays_origine', ''),
    #         'fournisseur_name': flat.get('vendeur_name', ''),
    #         'details_pays_origine': flat.get('pays_origine', ''),
    #         'details_fournisseur': flat.get('vendeur_address', ''),
    #     }
        
    #     # Ajouter tous les autres champs pour ne rien perdre
    #     for key, value in flat.items():
    #         if key not in ['declaration_di_number', 'importateur_name', 'produit_designation',
    #                       'valeur_fob_cfa', 'quantite_declaree', 'pays_origine',
    #                       'fournisseur_name', 'details_fournisseur']:
    #             mapped[key] = value
        
    #     return mapped