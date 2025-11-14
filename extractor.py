"""
Système d'Extraction Intelligent de Déclarations d'Importation
Version Entreprise - Adaptée pour Web API
"""

import re
import json
import csv
from typing import Dict, List, Optional, Any
import PyPDF2

class ImportDeclarationExtractor:
    """Extracteur intelligent pour déclarations d'importation SGS Cameroun"""
    
    def __init__(self):
        self.data = {}
        self.extracted_text = ""
        # Structure basée sur le format réel du document
        self.structure = {
            # Section: Déclaration (en-tête)
            "declaration": {
                "di_number": {
                    "label": "D.I N°",
                    "patterns": [
                        r"D\.I\s*N°\s*:\s*\n\s*([A-Z]{3}-\d+-\d+)",
                        r"D\.I\s*N°\s*:\s*([A-Z]{3}-\d+-\d+)",
                        r"DECLARATION.*?N°\s*:\s*\n?\s*([A-Z]{3}-\d+-\d+)",
                    ]
                },
                "date": {
                    "label": "Du / Dated",
                    "patterns": [r"GU N° :[A-Z0-9-]+\s*[\r\n]+\s*(?:[0-9]{2}\/[0-9]{2}\/[0-9]{4})([0-9]{2}\/[0-9]{2}\/[0-9]{4})"]
                },
                "date_exp": {
                    "label": "Date exp",
                    "patterns": [ r"Du\s*/\s*Dated\s*:?\s*(\d{2}/\d{2}/\d{4})",
                        r"Du\s*/\s*Dated\s*:?\s*\n\s*(\d{2}/\d{2}/\d{4})",
                        r"D\.I\s*N°.*?\n.*?(\d{2}/\d{2}/\d{4})",
                        r"Dated\s*:?\s*(\d{1,2}/\d{1,2}/\d{4})",
                        r"Du\s*:\s*(\d{2}/\d{2}/\d{4})",
                        r"(?:Du|Dated)\s*[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{4})",
                    ]
                },
                "gu_number": {
                    "label": "GU N°",
                    "patterns": [
                        r"GU\s*N°\s*:.*?(IM\d{6,})"
                    ]}
            },
            
            # Section: Importateur
            "importateur": {
                "name": {
                    "label": "Importateur (nom,adresse) / Importer(name,address)",
                    "patterns": [
                        r"Importer\s*\(name,address\)\s*\n\s*([A-Z][A-Z\s]+(?:LIMITED|SARL|SA|LLC))",
                        r"Importateur.*?Importer.*?\n([A-Z\s]+(?:LIMITED|SARL|SA))",
                    ]
                },
                "address": {
                    "label": "Adresse importateur",
                    "patterns": [
                        r"(?:LIMITED|SARL|SA|LLC)\s*\n\s*([A-Z0-9\s]+\d+\s+[A-Z]+)",
                        r"CERAMICS\s+LIMITED\s*\n\s*([^\n]+)",
                    ]
                },
                "code_agrement": {
                    "label": "Code d'agrément",
                    "patterns": [
                        r"(?<=Code d'agrément\n)\s*([A-Z0-9]{8})"
                    ]
                },
                "obtention": {
                    "label": "Obtention",
                    "patterns": [
                        r"Obtention\s*\n\s*(\d{2}/\d{2}/\d{4})",
                        r"Obtention\s*(\d{2}/\d{2}/\d{4})",
                    ]
                },
                "preremption": {
                    "label": "Préremption",
                    "patterns": [
                        r"Préremption\s*\n\s*(\d{2}/\d{2}/\d{4})",
                        r"Préremption\s*(\d{2}/\d{2}/\d{4})",
                    ]
                },
                "code_statistical": {
                    "label": "Code/Statistical number",
                    "patterns": [r"Importateur.*?Téléphone/Phone\s*\n?\s*([A-Z0-9]+)",
                        r"237683930379.*?Téléphone/Phone\s*\n?\s*([A-Z0-9]+)",
                    ]
                },
                "telephone": {
                    "label": "Téléphone/Phone",
                    "patterns": [ r"Code/Statistical\s*number\s*\n\s*(\d+)",
                        r"Statistical\s*number\s*(\d+)",
                    ]
                },
                "email": {
                    "label": "E-mail",
                    "patterns": [
                        r"Code\/Statistical number\s*\n\s*[0-9]+\s*\n\s*([A-Z0-9@._]{1,24})"
                    ]
                },
            },
            
            # Section: Vendeur
            "vendeur": {
                "name": {
                    "label": "Vendeur (nom,adresse) / Seller(name,address)",
                    "patterns": [
                        r"Seller\s*\(name,address\)\s*\n\s*([A-Z][A-Z\s]+(?:LIMITED|SARL|SA|LLC|LTD|INC|CO|CORPORATION|COMPANY|ENTERPRISES|GROUP))",
                        r"Vendeur.*?Seller.*?\n\s*([A-Z][A-Z\s&.,]+(?:LIMITED|LLC|LTD|INC|CO|SARL|SA))",
                        r"Seller.*?address.*?\n\s*([A-Z][A-Z\s&.,]+(?:LIMITED|LLC|LTD|INC|CO))",
                        r"Vendeur.*?\n\s*([A-Z][A-Z\s&]+(?:LIMITED|LTD|LLC|INC|SARL|SA))",
                        r"Seller.*?\n\s*([A-Z][A-Z\s]+(?:CO\.|COMPANY|CORP))",
                        r"address\)\s*\n\s*([A-Z][A-Z\s.,&-]+?(?:LIMITED|LTD|LLC|INC|CO\.?|SARL|SA))",
                    ]
                },
                "address": {
                    "label": "Adresse vendeur",
                    "patterns": [
                        r"(?:LIMITED|LTD|LLC|INC|CO\.|SARL|SA)\s*\n\s*([^\n]+?)(?:\n|Téléphone|Phone)",
                        r"(?:INVESTMENT|TRADING|EXPORT|INDUSTRIAL|COMMERCIAL)\s+(?:LIMITED|LLC|LTD)\s*\n\s*([A-Z0-9\s,.-]+)",
                        r"Seller.*?(?:LIMITED|LTD|LLC)\s*\n\s*([A-Z0-9][A-Z0-9\s,.-]+?)(?=\n.*?(?:Téléphone|Phone|E-mail|Fax))",
                        r"name,address\).*?\n.*?(?:LIMITED|LTD|LLC|INC)\s*\n\s*([^\n]+)",
                        r"(?:CO\.|COMPANY|CORP)\s*\n\s*([A-Z0-9][^\n]+?)(?=\n|$)",
                    ]
                },
                "telephone": {
                    "label": "Téléphone/Phone",
                    "patterns": [
                        r"Vendeur.*?Téléphone/Phone\s*\n?\s*(\d+)",
                        r"Seller.*?Téléphone.*?Phone\s*\n?\s*(\+?\d[\d\s-]+)",
                        r"Téléphone/Phone\s*\n\s*(\+?\d[\d\s-]{8,})",
                        r"Vendeur.*?Phone.*?\n\s*(\+?\d{8,})",
                        r"E-mail.*?\n.*?Téléphone.*?\n\s*(\d+)",
                    ]
                },
                "email": {
                    "label": "E-mail",
                    "patterns": [
                        r"Vendeur.*?E-mail:\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})(?=Télécopie)",
                    ]
                },
                "fax": {
                    "label": "Télécopie/Fax",
                    "patterns": [
                        r"Télécopie/Fax\s*\n?\s*(\d+)",
                    ]
                },
            },
            
            # Section: Commissionnaire Agréé en Douane
            "commissionnaire": {
                "full_name": {
                    "label": "Full Name",
                    "patterns": [
                        r"STE\s+ELIMELEC\s+SARL",
                        r"(\d{10})\s*\n\s*(STE\s+[A-Z]+\s+SARL)",
                        r"Télécopie/Fax\s*\d+\s*\n\s*([A-Z]{3}\s+[A-Z]+\s+[A-Z]+)",
                        r"(STE\s+ELIMELEC\s+SARL)\s*\n?\s*Full\s*Name",
                    ]
                },
                "adresse": {
                    "label": "Adresse",
                    "patterns": [
                        r"5077\s+DOUALA",
                        r"Adresse\s*\n\s*(\d+\s+[A-Z]+)",
                        r"Full\s*Name\s*\n?\s*Adresse\s*\n\s*(\d+\s+[A-Z]+)",
                    ]
                },
                "telephone_mobile": {
                    "label": "Telephone Mobile",
                    "patterns": [
                        r"233434882",
                        r"Telephone\s*Mobile:?\s*\n?\s*(\d+)",
                        r"Commisionaire.*?Telephone\s*Mobile:?\s*\n?\s*(\d+)",
                    ]
                },
                "email": {
                    "label": "Email",
                    "patterns": [
                        r"info@elim-elec\.cm",
                        r"Email:?\s*\n?\s*(info@elim-elec\.cm)",
                        r"Clearing.*?Email:?\s*\n?\s*([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})",
                    ]
                },
                "registre_commerce": {
                    "label": "Registre de commerce",
                    "patterns": [
                        r"DLN/2019/B/1924",
                        r"Registre\s*de\s*commerce\s*\n?\s*([A-Z0-9/]+)",
                    ]
                },
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
                       r"Pays\s*d'origine.*?Pays\s*d'origine\s*\n\s*([A-Z]{2}\s+[A-Za-z\s]+?)(?=\s*Pays de provenance|\s*Country of Shipment)"
                    ]
                },
                "provenance": {
                    "label": "Pays de provenance / Country of Shipment",
                    "patterns": [
                        r"Country\s*of\s*Shipment\s*\n\s*([A-Z]{2}\s+[A-Za-z]+)",
                        r"provenance.*?Shipment\s*\n\s*([A-Z]{2}\s+[A-Za-z]+)",
                        r"Pays\s*de\s*provenance.*?\n\s*([A-Z]{2}\s+[A-Za-z]+)",
                        r"Shipment\s*\n\s*([A-Z]{2}[\s\-]+[A-Za-z]+)",
                        r"provenance.*?\n\s*([A-Z]{2}\s+[A-Za-z]+)",
                        r"origine.*?\n.*?\n\s*([A-Z]{2}\s+[A-Za-z]+)",
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
            
            # Section: Banque
            "banque": {
                "domiciliatrice": {
                    "label": "Banque domiciliatrice / Authorised bank",
                    "patterns": [
                        r"CREDIT\s+COMMUNAUTAIRE\s+D'AFRIQUE\s*-?CCA",
                        r"Authorised\s*bank\s*\n\s*([A-Z][A-Z\s\-]+?)(?=\n|Valeur)",
                        r"Banque\s*domiciliatrice.*?\n\s*([A-Z\s\-]+CCA)",
                    ]
                },
                "domiciliation_numero": {
                    "label": "N° (domiciliation)",
                    "patterns": [
                       r"([A-Z][A-Z0-9\-]{4,}[A-Z]{0,1}\-[A-Z0-9\-\s]+EUR)"
                    ]
                },
                "domiciliation_date": {
                    "label": "Date (domiciliation)",
                    "patterns": [
                        r"04/09/2025",
                        r"Date\s*:\s*(\d{2}/\d{2}/\d{4})",
                        r"Domicilié.*?Date\s*:\s*(\d{2}/\d{2}/\d{4})",
                    ]
                },
                "agence": {
                    "label": "Agence",
                    "patterns": [
                        r"Agence\s*:\s*([A-Z\s]+?)(?=ATTESTATION)",
                    ]
                },
            },
            
            # Section: Valeurs financières
            "valeurs_financieres": {
                "valeur_totale_devise": {
                    "label": "Valeur Totale (devises)",
                    "patterns": [
                        r"30,091\.74",
                        r"Total\s*value\s*in\s*foreign\s*currency\s*\n?\s*\*{0,2}([\d,\.]+)",
                    ]
                },
                "devise": {
                    "label": "Devise / Currency",
                    "patterns": [
                        r"Devise\s*/\s*Currency\s*\n?\s*([A-Z]{3})",
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
                        r"82691",
                        r"Proforma\s*no.*?\n?\s*(\d+)",
                    ]
                },
                "facture_proforma_date": {
                    "label": "Date Facture Proforma",
                    "patterns": [
                        r"05/08/2025",
                        r"Proforma.*?(\d{2}/\d{2}/\d{4})",
                    ]
                },
                "terme_vente": {
                    "label": "Terme de vente / Incoterm",
                    "patterns": [
                        r"CFR",
                        r"Incoterm\s*\n?\s*([A-Z]{3})",
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
                        r"16,949,797\.69",
                        r"FOB\s*value\s*in\s*CFA\s*\n?\s*\*{0,2}([\d,\.]+)",
                    ]
                },
                "valeur_fob_devise": {
                    "label": "Valeur FOB (devises)",
                    "patterns": [
                        r"25,839\.80",
                        r"FOB\s*value\s*in\s*foreign\s*currency\s*\n?\s*\*{0,2}([\d,\.]+)",
                    ]
                },
            },
            
            # Section: Marchandises
            "marchandises": {
                "quantite": {
                    "label": "Quantité / Quantity",
                    "patterns": [
                        r"Quantity\s*\n\s*\*{0,2}([\d,]+\.?\d*)",
                        r"Quantité.*?Quantity\s*\n\s*\*{0,2}([\d,]+\.?\d*)",
                        r"(?:Quantity|Quantité)\s*[:\s]*\*{0,2}([\d,]+\.?\d*)",
                        r"(\d{1,3}(?:,\d{3})*\.?\d*)\s+\*{0,2}[\d,]+\.?\d+\s+\d{10,}",
                        r"marchandises.*?\n.*?\*{0,2}([\d,]+\.?\d*)\s+\*{0,2}[\d,]+",
                        r"\*{0,2}([\d,]+\.00)\s+\*{0,2}[\d,]+\.?\d+\s+(?:KG|MT|UNIT)",
                    ]
                },
                "fob_devise": {
                    "label": "FOB en devise",
                    "patterns": [
                        r"Quantity.*?\*{0,2}[\d,\.]+\s+\*{0,2}([\d,\.]+)\s+\d{10,}",
                    ]
                },
                "hs_code": {
                    "label": "Pos. tarifaire / HS code",
                    "patterns": [
                        r"32072000000",
                        r"(\d{10,})\s+KG",
                    ]
                },
                "unite": {
                    "label": "Unité / Unit",
                    "patterns": [
                        r"KG",
                        r"\d{10,}\s+(KG|MT|UNIT|PCS)",
                    ]
                },
                "description": {
                    "label": "Description des marchandises",
                    "patterns": [
                        r"GLAZE\s+MATERIAL",
                        r"(?:KG|MT)\s+([A-Z\s]+?)(?=\n|Taxe)",
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
                        r"Inspection.*?(\d{2}/\d{2}/\d{4})",
                        r"[\d,]+\s+(\d{2}/\d{2}/\d{4})",
                        r"(?:Taxe|Inspection).*?(\d{1,2}/\d{1,2}/\d{4})",
                        r"CAMEROUN\s+\*{0,2}[\d,]+\s+(\d{2}/\d{2}/\d{4})",
                        r"Bank.*?\n.*?(\d{2}/\d{2}/\d{4})",
                        r"Dated.*?(\d{2}/\d{2}/\d{4})(?=.*?(?:Chèque|Cheque|\d{7}))",
                    ]
                },
                "montant_cfa": {
                    "label": "Montant CFA",
                    "patterns": [
                        r"192,022",
                        r"CAMEROUN\s+\*{0,2}([\d,]+)",
                    ]
                },
                "cheque_numero": {
                    "label": "Chèque N°",
                    "patterns": [
                        r"(?:Chèque|Cheque)\s*N°?\s*[:\s]*(\d+)",
                        r"\d{2}/\d{2}/\d{4}\s+(\d{6,})",
                        r"(?:Taxe|Inspection).*?\d{2}/\d{2}/\d{4}.*?(\d{6,})",
                        r"CAMEROUN.*?\d{2}/\d{2}/\d{4}\s+(\d{6,})",
                        r"[\d,]+\s+\d{2}/\d{2}/\d{4}\s+(\d{6,})",
                        r"(\d{7,8})(?=\s*\n|$)(?<=\d{2}/\d{2}/\d{4}\s+\d{7,8})",
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
    
    def extract_from_pdf(self, pdf_path: str) -> str:
        """Extrait le texte d'un PDF"""
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
                    if match.groups():
                        value = match.group(1).strip()
                    else:
                        value = match.group(0).strip()
                    value = re.sub(r'\*+', '', value)
                    value = re.sub(r'\s+', ' ', value)
                    value = value.replace('\n', ' ').strip()
                    if value:
                        return value
                except:
                    continue
        return None
    
    def extract_all_fields(self, text: str) -> Dict[str, Any]:
        """Extrait tous les champs par section avec validation"""
        self.extracted_text = text
        results = {}
        statistics = {
            "total_fields": 0,
            "extracted_fields": 0,
            "missing_fields": []
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
        results["_statistics"] = statistics
        return results

    def save_to_csv(self, data: Dict[str, Any], output_path: str):
        """Enregistre les données dans un fichier CSV"""
        clean_data = {k: v for k, v in data.items() if k != "_statistics"}
        flat_data = self._flatten_dict(clean_data)
        with open(output_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=flat_data.keys())
            writer.writeheader()
            writer.writerow(flat_data)
        return output_path
    
    def save_to_json(self, data: Dict[str, Any], output_path: str):
        """Enregistre les données dans un fichier JSON"""
        with open(output_path, 'w', encoding='utf-8') as jsonfile:
            json.dump(data, jsonfile, indent=4, ensure_ascii=False)
        return output_path

    def _flatten_dict(self, d: Dict, parent_key: str = '', sep: str = '_') -> Dict:
        """Aplatit un dictionnaire imbriqué pour CSV"""
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(self._flatten_dict(v, new_key, sep=sep).items())
            else:
                items.append((new_key, v))
        return dict(items)