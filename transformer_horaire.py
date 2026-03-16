import pandas as pd


def heure_str_vers_minutes(heure_str):
    """Convertit une chaîne 'HH:MM' ou 'HHhMM' en minutes depuis minuit."""
    if pd.isna(heure_str) or str(heure_str).strip() == "":
        return 0
    try:
        # Normalise le format en remplaçant 'h' par ':'
        h_str = str(heure_str).replace('h', ':')
        h, m = map(int, h_str.split(':'))
        return h * 60 + m
    except (ValueError, AttributeError):
        return 0

def parser_plage_horaire(plage_str):
    """
    Analyse une chaîne comme '09:00-12:00' et la convertit en un tuple de minutes (ouverture, fermeture).
    Gère les cas où la donnée est absente, invalide ou marquée 'FERME'.
    """
    # Si la case est vide, contient 'FERME', ou est invalide, on retourne (0, 0)
    if pd.isna(plage_str) or 'FERME' in str(plage_str).upper() or '-' not in str(plage_str):
        return 0, 0
    
    try:
        ouv_str, ferm_str = plage_str.split('-')
        ouverture_min = heure_str_vers_minutes(ouv_str.strip())
        fermeture_min = heure_str_vers_minutes(ferm_str.strip())
        return ouverture_min, fermeture_min
    except (ValueError, AttributeError):
        # Sécurité en cas de format inattendu
        return 0, 0
