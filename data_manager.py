import pandas as pd
import os
import uuid
from datetime import datetime

class DataManager:
    """
    Gère la persistance des données dans un fichier CSV (CRUD).
    Simule une base de données simple.
    """
    
    # Définition des colonnes de base (schéma de la DB)
    DEFAULT_COLUMNS = [
        'record_id', 'date_ajout', 'declaration_di_number', 'importateur_name', 
        'produit_designation', 'valeur_fob_cfa', 'quantite_declaree', 
        'pays_origine', 'fournisseur_name', 'details_pays_origine', 
        'details_fournisseur', 'document_path'
    ]

    def __init__(self, db_path):
        self.db_path = db_path
        self._initialize_db()

    def _initialize_db(self):
        """Initialise le fichier CSV s'il n'existe pas."""
        if not os.path.exists(self.db_path):
            self.df = pd.DataFrame(columns=self.DEFAULT_COLUMNS)
            # Sauvegarde avec les colonnes vides
            self.df.to_csv(self.db_path, index=False)
        else:
            try:
                # Tente de charger le fichier existant
                self.df = pd.read_csv(self.db_path, dtype=str)
                # S'assurer que les colonnes par défaut sont présentes
                for col in self.DEFAULT_COLUMNS:
                    if col not in self.df.columns:
                        self.df[col] = ''
                # Réordonner les colonnes
                self.df = self.df[self.DEFAULT_COLUMNS + [col for col in self.df.columns if col not in self.DEFAULT_COLUMNS]]

            except pd.errors.EmptyDataError:
                # Si le fichier est vide
                self.df = pd.DataFrame(columns=self.DEFAULT_COLUMNS)
            except Exception as e:
                print(f"Erreur lors du chargement de la DB: {e}. Création d'une nouvelle DB vide.")
                self.df = pd.DataFrame(columns=self.DEFAULT_COLUMNS)
        
        # S'assurer que l'ID est la clé principale
        if 'record_id' not in self.df.columns:
             self.df['record_id'] = [str(uuid.uuid4()) for _ in range(len(self.df))]

    def _save_db(self):
        """Sauvegarde le DataFrame dans le fichier CSV."""
        self.df.to_csv(self.db_path, index=False)

    def add_record(self, data: dict):
        """Ajoute un nouvel enregistrement."""
        new_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()
        
        # Création d'un dictionnaire pour le nouvel enregistrement avec les métadonnées
        new_record = {
            'record_id': new_id,
            'date_ajout': timestamp,
        }
        
        # Ajout des données extraites (s'assurer que toutes les clés sont des chaînes)
        for key, value in data.items():
            new_record[key] = str(value) if value is not None else ''

        # Convertir le dictionnaire en DataFrame d'une seule ligne
        new_row_df = pd.DataFrame([new_record])
        
        # Assurer que toutes les colonnes par défaut sont présentes dans la nouvelle ligne
        for col in self.DEFAULT_COLUMNS:
            if col not in new_row_df.columns:
                new_row_df[col] = ''
        
        # Concaténer la nouvelle ligne
        self.df = pd.concat([self.df, new_row_df], ignore_index=True)
        self._save_db()
        return new_id

    def get_all_records(self) -> pd.DataFrame:
        """Retourne tous les enregistrements."""
        return self.df.sort_values(by='date_ajout', ascending=False)

    def update_record(self, record_id: str, updated_data: dict):
        """Met à jour un enregistrement par son ID."""
        if 'record_id' not in self.df.columns:
            raise ValueError("La colonne 'record_id' est manquante.")
            
        index = self.df[self.df['record_id'] == record_id].index
        
        if index.empty:
            raise ValueError(f"Enregistrement avec ID {record_id} non trouvé.")

        for key, value in updated_data.items():
            # Mise à jour de la colonne si elle existe
            if key in self.df.columns:
                self.df.loc[index, key] = str(value) if value is not None else ''
            else:
                 # Ajout d'une nouvelle colonne si elle n'existe pas
                 self.df[key] = ''
                 self.df.loc[index, key] = str(value) if value is not None else ''

        self._save_db()

    def delete_record(self, record_id: str):
        """Supprime un enregistrement par son ID."""
        initial_len = len(self.df)
        self.df = self.df[self.df['record_id'] != record_id]
        
        if len(self.df) == initial_len:
            raise ValueError(f"Enregistrement avec ID {record_id} non trouvé.")
            
        self._save_db()

    def search_records(self, term: str, column: str = None) -> pd.DataFrame:
        """Recherche des enregistrements par terme dans une colonne spécifique ou toutes les colonnes."""
        term = str(term).strip().lower()
        if not term:
            return pd.DataFrame(columns=self.DEFAULT_COLUMNS) # Retourne un DF vide
        
        # Remplacer les NaN par des chaînes vides pour la recherche
        temp_df = self.df.fillna('')

        if column and column in temp_df.columns:
            # Recherche dans une colonne spécifique
            results = temp_df[temp_df[column].str.lower().str.contains(term, na=False)]
        else:
            # Recherche dans toutes les colonnes
            mask = temp_df.apply(
                lambda row: row.astype(str).str.lower().str.contains(term, na=False).any(), axis=1
            )
            results = temp_df[mask]

        return results.sort_values(by='date_ajout', ascending=False)