import streamlit as st
import pandas as pd
import numpy as np

import optimisation_tournee




def charger_dates_valides():
    """
    Lit le fichier d'horaires et retourne une liste des dates uniques et valides
    pour lesquelles il existe des données.
    """
    try:
        horaires_file = "synthese_horaires_sites.csv"
        df_horaires = pd.read_csv(horaires_file, sep=';', encoding='utf-8')
        
        # Convertit la colonne en dates, les formats invalides deviennent NaT (Not a Time)
        df_horaires['Date_calendrier'] = pd.to_datetime(df_horaires['Date_calendrier'], format='%d/%m/%Y', errors='coerce')
        
        # Supprime les lignes où la date n'a pas pu être interprétée
        df_horaires.dropna(subset=['Date_calendrier'], inplace=True)
        
        # Récupère les dates uniques et les trie
        dates_uniques = sorted(df_horaires['Date_calendrier'].unique())
        
        if dates_uniques:
            return dates_uniques[0].strftime("%d %m %Y"), dates_uniques[-1].strftime("%d %m %Y") # Retourne (min_date, max_date)
        return None, None
    except FileNotFoundError:
        st.error("Fichier `synthese_horaires_sites.csv` introuvable. Impossible de déterminer les dates valides.")
        return None, None

def check_mot_de_passe() : 
    """Vérifie si l'utilisateur a rentré le bon mdp"""

    def mot_de_passe_entered():
        """Vérifie le mdp tapé par l'utilisateur """
        if st.session_state["password"] == st.secrets["mot_de_passe"] :
            st.session_state["password_correct"] = True
            del st.session_state["password"]

        else : 
            st.session_state["password_correct"] = False
        
    if "password_correct" not in st.session_state : 
        st.text_input("Veuillez entrer un mot de passe :", type="password", on_change=mot_de_passe_entered, key="password")
        return False
    elif not st.session_state["password_correct"] : 
        st.text_input("Veuillez entrer un mot de passe :", type="password", on_change=mot_de_passe_entered, key="password")
        st.error("mot de passe incorrect ")
        return False
    else :
        return True 


#CHARGEMENT DES DONNÉES

def charger_donnees(date_selectionnee):
    try:
        sites_file = "sites.csv"
        durations_file = "durations.csv"
        distances_file = "distance.csv"
        home_site_durations_file = "durations_sites_maison.csv"
        tournees_file = "tournees.csv"
        horaires_file = "synthese_horaires_sites.csv"

        df_sites_original = pd.read_csv(sites_file, sep=';', encoding="utf-8")
        
        df_durees_temp = pd.read_csv(durations_file, sep=';', encoding='utf-8')
        df_durees_temp = df_durees_temp[df_durees_temp['id']>0]
        df_durees_temp = df_durees_temp.drop('nom',axis=1)
        df_durees_temp = df_durees_temp.drop('cluster',axis=1)

        df_distances_temp = pd.read_csv(distances_file, sep=';', encoding='utf-8')
        df_home_site_durations_temp = pd.read_csv(home_site_durations_file, sep=';', encoding='latin-1')
        df_tournees = pd.read_csv(tournees_file, sep=';', encoding='latin-1')
        df_horaires_temp = pd.read_csv(horaires_file, sep=';', encoding='utf-8')


    except FileNotFoundError as e:
        st.error(f"Fichier manquant : {e}. Veuillez vérifier que tous les CSV sont présents.")
        return pd.DataFrame(),pd.DataFrame()
    
    

    df_horaires = df_horaires_temp.copy()
    df_horaires['Date_calendrier'] = pd.to_datetime(df_horaires['Date_calendrier'], format='%d/%m/%Y', errors='coerce')
    horaires_du_jour = df_horaires[df_horaires['Date_calendrier'].dt.date == date_selectionnee].copy()

    #Fusion des données
    df_merged = pd.merge(df_sites_original, df_tournees, left_on='cluster', right_on='numTournée', how='left')
    
    horaires_du_jour = horaires_du_jour.drop(['NomSite','Typologie MTK'], axis=1)
    df_merged = pd.merge(df_merged, horaires_du_jour, on='idSite', how='left')

    #CRÉATION DU DATAFRAME FINAL 'df_sites'
    df_sites = pd.DataFrame()
    df_sites["ID_Site"] = df_merged["idSite"]
    df_sites["Nom"] = df_merged["NomSite"]
    df_sites["Groupement"] = df_merged["nom"]
    temps_pec_heures = pd.to_numeric(df_merged["Nb_Heures"].str.replace(',', '.'), errors='coerce').fillna(0)
    df_sites["Temps_PEC"] = (temps_pec_heures * 60).astype(int)
    df_sites["Maint_Prev"] = 0 
    df_sites["Maint_Corr"] = 0 

    
    # Définition des horaires par défaut en minutes
    default_ouv_matin = 480  # 08:00
    default_ferm_matin = 720  # 12:00
    default_ouv_aprem = 810  # 13:30
    default_ferm_aprem = 1020 # 17:00
    default_horaires_str = "08:00-12:00 | 13:30-17:00 (Défaut)"

    # Condition : identifier les lignes où aucune info d'horaire n'a été trouvée
    sans_horaires_definis = pd.isna(df_merged['Date_calendrier'])


    # Pour l'ouverture du matin
    ouv_matin_reels = df_merged['Plage_horaire_1'].apply(optimisation_tournee.transformer_horaire.parser_plage_horaire).apply(lambda x: x[0])
    df_sites['Ouv_Matin'] = np.where(sans_horaires_definis, default_ouv_matin, ouv_matin_reels)

    # Pour la fermeture du matin
    ferm_matin_reels = df_merged['Plage_horaire_1'].apply(optimisation_tournee.transformer_horaire.parser_plage_horaire).apply(lambda x: x[1])
    df_sites['Ferm_Matin'] = np.where(sans_horaires_definis, default_ferm_matin, ferm_matin_reels)

    # Pour l'ouverture de l'après-midi
    ouv_aprem_reels = df_merged['Plage_horaire_2'].apply(optimisation_tournee.transformer_horaire.parser_plage_horaire).apply(lambda x: x[0])
    df_sites['Ouv_Aprem'] = np.where(sans_horaires_definis, default_ouv_aprem, ouv_aprem_reels)
    
    # Pour la fermeture de l'après-midi
    ferm_aprem_reels = df_merged['Plage_horaire_2'].apply(optimisation_tournee.transformer_horaire.parser_plage_horaire).apply(lambda x: x[1])
    df_sites['Ferm_Aprem'] = np.where(sans_horaires_definis, default_ferm_aprem, ferm_aprem_reels)

    # --- 6. CRÉATION DE LA COLONNE 'Horaires' LISIBLE (MODIFIÉ) ---
    def formater_horaires_display(row):
        h1 = row['Plage_horaire_1']
        h2 = row['Plage_horaire_2']
        if 'FERME' in str(h1).upper(): return "Fermé"
        horaires_str = str(h1).strip() if pd.notna(h1) else ""
        if pd.notna(h2) and str(h2).strip() != '': horaires_str += f" | {h2.strip()}"
        return horaires_str

    horaires_reels_str = df_merged.apply(formater_horaires_display, axis=1)
    df_sites['Horaires'] = np.where(sans_horaires_definis, default_horaires_str, horaires_reels_str)

    df_sites["Dans_Tournee_Defaut"] = False 

    return df_sites,df_durees_temp




#INTERFACE STREAMLIT
if check_mot_de_passe():
    st.success('Accès autorisé')
    st.set_page_config(page_title="Gestion Tournées Techniciens", layout="wide")
    min_date, max_date = charger_dates_valides()


    # Initialisation du session_state
    if 'horaire_tech' not in st.session_state : #Horaire du technicien en str
        st.session_state.horaire_tech = "00:00-12:00"
    if 'etape' not in st.session_state:
        st.session_state.etape = 1
    if 'sites_courants' not in st.session_state: #sites dans le cluster 
        st.session_state.sites_courants = pd.DataFrame()
    if 'resultat_tournee' not in st.session_state:
        st.session_state.resultat_tournee = None
    if 'groupement_choisi' not in st.session_state: #ou cluster
        st.session_state.groupement_choisi = "Grenoble"
    if 'site' not in st.session_state:
        st.session_state.site = pd.DataFrame()
    if 'duration' not in st.session_state:
        st.session_state.duration = pd.DataFrame()
    if 'tech' not in st.session_state:
        st.session_state.tech = ""


    #1ère page : choix de la date
    if st.session_state.etape == 1:
        st.header("Choix de la journée")
        st.subheader(f"Choisir une date entre : {min_date} et {max_date}")
        date = st.date_input("Date d'intervention")
        
        if st.button("✅ Valider cette date"):
            try:
                sites_file = "sites.csv"
                durations_file = "durations.csv"
                distances_file = "distance.csv"
                home_site_durations_file = "durations_sites_maison.csv"
                tournees_file = "tournees.csv"
                horaires_file = "synthese_horaires_sites.csv"
        
                df_sites_original = pd.read_csv(sites_file, sep=';', encoding="utf-8")
                
                df_durees_temp = pd.read_csv(durations_file, sep=';', encoding='utf-8')
                df_durees_temp = df_durees_temp[df_durees_temp['id']>0]
                df_durees_temp = df_durees_temp.drop('nom',axis=1)
                df_durees_temp = df_durees_temp.drop('cluster',axis=1)
        
                df_distances_temp = pd.read_csv(distances_file, sep=';', encoding='utf-8')
                df_home_site_durations_temp = pd.read_csv(home_site_durations_file, sep=';', encoding='latin-1')
                df_tournees = pd.read_csv(tournees_file, sep=';', encoding='latin-1')
                df_horaires_temp = pd.read_csv(horaires_file, sep=';', encoding='utf-8')
        
        
            except FileNotFoundError as e:
                st.error(f"Fichier manquant : {e}. Veuillez vérifier que tous les CSV sont présents.")
                st.session_state.site = pd.DataFrame()
                st.session_state.duration  = pd.DataFrame()
            
            
        
            df_horaires = df_horaires_temp.copy()
            df_horaires['Date_calendrier'] = pd.to_datetime(df_horaires['Date_calendrier'], format='%d/%m/%Y', errors='coerce')
            horaires_du_jour = df_horaires[df_horaires['Date_calendrier'].dt.date == date].copy()
        
            #Fusion des données
            df_merged = pd.merge(df_sites_original, df_tournees, left_on='cluster', right_on='numTournée', how='left')
            
            horaires_du_jour = horaires_du_jour.drop(['NomSite','Typologie MTK'], axis=1)
            df_merged = pd.merge(df_merged, horaires_du_jour, on='idSite', how='left')
        
            #CRÉATION DU DATAFRAME FINAL 'df_sites'
            df_sites = pd.DataFrame()
            df_sites["ID_Site"] = df_merged["idSite"]
            df_sites["Nom"] = df_merged["NomSite"]
            df_sites["Groupement"] = df_merged["nom"]
            temps_pec_heures = pd.to_numeric(df_merged["Nb_Heures"].str.replace(',', '.'), errors='coerce').fillna(0)
            df_sites["Temps_PEC"] = (temps_pec_heures * 60).astype(int)
            df_sites["Maint_Prev"] = 0 
            df_sites["Maint_Corr"] = 0 
        
            
            # Définition des horaires par défaut en minutes
            default_ouv_matin = 480  # 08:00
            default_ferm_matin = 720  # 12:00
            default_ouv_aprem = 810  # 13:30
            default_ferm_aprem = 1020 # 17:00
            default_horaires_str = "08:00-12:00 | 13:30-17:00 (Défaut)"
        
            # Condition : identifier les lignes où aucune info d'horaire n'a été trouvée
            sans_horaires_definis = pd.isna(df_merged['Date_calendrier'])
        
        
            # Pour l'ouverture du matin
            ouv_matin_reels = df_merged['Plage_horaire_1'].apply(optimisation_tournee.transformer_horaire.parser_plage_horaire).apply(lambda x: x[0])
            df_sites['Ouv_Matin'] = np.where(sans_horaires_definis, default_ouv_matin, ouv_matin_reels)
        
            # Pour la fermeture du matin
            ferm_matin_reels = df_merged['Plage_horaire_1'].apply(optimisation_tournee.transformer_horaire.parser_plage_horaire).apply(lambda x: x[1])
            df_sites['Ferm_Matin'] = np.where(sans_horaires_definis, default_ferm_matin, ferm_matin_reels)
        
            # Pour l'ouverture de l'après-midi
            ouv_aprem_reels = df_merged['Plage_horaire_2'].apply(optimisation_tournee.transformer_horaire.parser_plage_horaire).apply(lambda x: x[0])
            df_sites['Ouv_Aprem'] = np.where(sans_horaires_definis, default_ouv_aprem, ouv_aprem_reels)
            
            # Pour la fermeture de l'après-midi
            ferm_aprem_reels = df_merged['Plage_horaire_2'].apply(optimisation_tournee.transformer_horaire.parser_plage_horaire).apply(lambda x: x[1])
            df_sites['Ferm_Aprem'] = np.where(sans_horaires_definis, default_ferm_aprem, ferm_aprem_reels)
        
            # --- 6. CRÉATION DE LA COLONNE 'Horaires' LISIBLE (MODIFIÉ) ---
            def formater_horaires_display(row):
                h1 = row['Plage_horaire_1']
                h2 = row['Plage_horaire_2']
                if 'FERME' in str(h1).upper(): return "Fermé"
                horaires_str = str(h1).strip() if pd.notna(h1) else ""
                if pd.notna(h2) and str(h2).strip() != '': horaires_str += f" | {h2.strip()}"
                return horaires_str
        
            horaires_reels_str = df_merged.apply(formater_horaires_display, axis=1)
            df_sites['Horaires'] = np.where(sans_horaires_definis, default_horaires_str, horaires_reels_str)
        
            df_sites["Dans_Tournee_Defaut"] = False
            st.session_state.site =df_sites
            st.session_state.duration  = df_durees_temp
            st.session_state.etape = 2
            st.rerun()
        


    # PARAMÉTRAGE
    if st.session_state.etape == 2:
        df_tournees = pd.read_csv("tournees.csv", sep=';', encoding='latin-1')
        df_techniciens = pd.read_csv("technicien.csv", sep=';', encoding='latin-1')
        df_techniciens['prenom nom']=df_techniciens['prenom'] + ' ' + df_techniciens['nom']

        st.header("Choix de la Tournée")

        col1, col2 = st.columns(2)
        with col1:
            st.session_state.tech = st.selectbox("Technicien", df_techniciens['prenom nom'].tolist())
            num_tournee =  df_techniciens[df_techniciens['prenom nom'] == st.session_state.tech]['tourne_defaut'].iloc[0]
            
            st.text(f"Zone géographique du technicien : { df_tournees[df_tournees['numTournée']==num_tournee]['nom'].iloc[0]}")
            groupement = st.selectbox("Groupement géographique",df_tournees['nom'].tolist())
            st.session_state.groupement_choisi = groupement

        with col2:
            
            liste_matin = ["07:00","07:30","08:00","08:30","09:00","09:30","10:00","11:00","12:00","13:00","14:00"]
            liste_aprem = ["12:00","13:00","13:30","14:00","15:00","16:00","16:30","17:00","17:30","18:00"]
            
            matin = st.selectbox("Heure début de journée",liste_matin)
            aprem = st.selectbox("Heure fin de journée",liste_aprem)
            st.markdown("*La pause du midi dure 1h30 entre 12h et 14h*.")
            st.session_state.horaire_tech = matin+"-"+aprem
        
        
        st.subheader(f"Ajustement des interventions : {groupement}")
        col1, col2,_,_ = st.columns(4)
        with col1:
            #st.text(f"💡Recommendation : \nSi les durées sont trop longues à cette étape, le système bloquera en jugeant la journée irrealisable (à cause des contraintes d'horaires ou de temps de trajet). Pour cela, saisissez un temps de service total minime que vous ajusterez plus tard")
            st.text(f"⚠️Tous les temps sont en minutes \nLe technicien travaille 7h30 dans sa journée = 450 minutes")
        with col2:
            st.text(f"Temps_PEC par défaut est le temps (en minute) prévu pour la prise en charge")
            
    
        sites_du_groupe = st.session_state.site[st.session_state.site["Groupement"] == groupement].copy()
        sites_du_groupe["À_Visiter"] = sites_du_groupe["Dans_Tournee_Defaut"]
    
        colonnes_visibles = ["À_Visiter", "Nom", "Horaires", "Temps_PEC", "Maint_Prev", "Maint_Corr"]
        edited_df = st.data_editor(sites_du_groupe[colonnes_visibles], hide_index=True, width='stretch')
    
        if st.button("🚀 Calculer l'itinéraire"):
            sites_coches = edited_df[edited_df["À_Visiter"] == True].copy()
            sites_coches["Temps_Total_Service"] = sites_coches["Temps_PEC"] + sites_coches["Maint_Prev"] + sites_coches["Maint_Corr"]
        
            noms_choisis = sites_coches["Nom"].tolist()
            details_sites = st.session_state.site[st.session_state.site["Nom"].isin(noms_choisis)][['ID_Site',"Nom", "Ouv_Matin", "Ferm_Matin", "Ouv_Aprem", "Ferm_Aprem"]]
            sites_finaux = pd.merge(sites_coches, details_sites, on="Nom")
        
            st.session_state.sites_courants = sites_finaux
            st.session_state.resultat_tournee = optimisation_tournee.optimiser_tournee(st.session_state.sites_courants,st.session_state.duration,st.session_state.horaire_tech)
            
            st.session_state.etape = 3
            st.rerun()
        if st.button("🔄 Changer la date"):
                st.session_state.etape = 1
                st.session_state.sites_courants = pd.DataFrame()
                st.session_state.resultat_tournee = None
                st.session_state.etape = 1 
                st.rerun()

    # --- ÉTAPE 2 : ATELIER D'AJUSTEMENT ---
    elif st.session_state.etape == 3:
        st.header("2. Ajustement de la Tournée")
        st.session_state.sites_courants["Temps_Total_Service"] = st.session_state.sites_courants["Temps_PEC"] + st.session_state.sites_courants["Maint_Prev"] + st.session_state.sites_courants["Maint_Corr"]
        tournee_courante = optimisation_tournee.optimiser_tournee(st.session_state.sites_courants,st.session_state.duration,st.session_state.horaire_tech)


    
        col_tournee, col_suggestions = st.columns([2, 1])
    
        with col_tournee:
            st.subheader("Planning calculé")
            if (len(st.session_state.sites_courants) == 0) : 
                st.error("Aucun site dans la tournée")
                st.session_state.sites_courants["Heure_Arrivee"] = None
                st.session_state.sites_courants["Heure_Fin"] = None

            elif (len(st.session_state.sites_courants) == 1) : 
                st.error("Un seul site -> pas d'optimisation de tournée")
                st.session_state.sites_courants["Heure_Arrivee"] = None
                st.session_state.sites_courants["Heure_Fin"] = None

            elif tournee_courante is not None:

                print('################################')

                print(st.session_state.sites_courants)
                st.session_state.sites_courants['Heure_Arrivee'] = None
                st.session_state.sites_courants['Heure_Fin'] = None
                st.session_state.sites_courants['Ordre'] = None
                st.session_state.sites_courants = st.session_state.sites_courants.drop('Heure_Arrivee', axis=1)
                st.session_state.sites_courants = st.session_state.sites_courants.drop('Heure_Fin', axis=1)
                st.session_state.sites_courants = st.session_state.sites_courants.drop('Ordre', axis=1)
                colonnes_a_joindre = tournee_courante[['ID_Site', 'Heure_Arrivee', 'Heure_Fin','Ordre']]

                print(st.session_state.sites_courants)

                
                st.session_state.sites_courants = pd.merge(
                    st.session_state.sites_courants,
                    colonnes_a_joindre,
                    on='ID_Site',       # La colonne commune pour la correspondance
                    how='left'          # 'left' pour garder toutes les lignes de la table de gauche
                    
                )
                print(st.session_state.sites_courants)

                
            else:
                st.error("⚠️ Alerte : Le planning est surchargé ou les horaires ne permettent pas de tout caser.")
                st.session_state.sites_courants["Heure_Arrivee"] = None
                st.session_state.sites_courants["Heure_Fin"] = None
                st.session_state.sites_courants["Ordre"] = None

            if st.session_state.sites_courants["Ordre"] is not None :
                st.session_state.sites_courants.sort_values('Ordre', ascending=True, inplace=True)

            colonnes_visibles = ["Nom", "Horaires", "Temps_PEC", "Maint_Prev", "Maint_Corr","Temps_Total_Service","Heure_Arrivee","Heure_Fin"]
            edited_df = st.data_editor(st.session_state.sites_courants[colonnes_visibles], hide_index=True, width='stretch')
            
            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("⬅️ Modifier la sélection"):
                    st.session_state.etape = 2
                    st.rerun()
            with col_btn2:
                if st.button("🔄 Recalculer"):
                    edited_df["Temps_Total_Service"] = edited_df["Temps_PEC"] + edited_df["Maint_Prev"] + edited_df["Maint_Corr"]
                    noms_choisis = edited_df["Nom"].tolist()
                    details_sites = st.session_state.site[st.session_state.site["Nom"].isin(noms_choisis)][['ID_Site',"Nom", "Ouv_Matin", "Ferm_Matin", "Ouv_Aprem", "Ferm_Aprem"]]

                    sites_finaux = pd.merge(edited_df, details_sites, on="Nom")
                    st.session_state.sites_courants = sites_finaux

                    st.rerun()
                if st.button("✅ Valider ce planning"):

                    edited_df["Temps_Total_Service"] = edited_df["Temps_PEC"] + edited_df["Maint_Prev"] + edited_df["Maint_Corr"]
                    noms_choisis = edited_df["Nom"].tolist()
                    details_sites = st.session_state.site[st.session_state.site["Nom"].isin(noms_choisis)][['ID_Site',"Nom", "Ouv_Matin", "Ferm_Matin", "Ouv_Aprem", "Ferm_Aprem"]]

                    sites_finaux = pd.merge(edited_df, details_sites, on="Nom")
                    st.session_state.sites_courants = sites_finaux

                    st.session_state.resultat_tournee = tournee_courante
                    st.session_state.etape = 4
                    st.rerun()
                

        with col_suggestions:
            st.subheader("💡 Suggestions")
            if st.button("✨ Remplir la journée automatiquement", type="primary"):
                edited_df["Temps_Total_Service"] = edited_df["Temps_PEC"] + edited_df["Maint_Prev"] + edited_df["Maint_Corr"]
                noms_choisis = edited_df["Nom"].tolist()
                details_sites = st.session_state.site[st.session_state.site["Nom"].isin(noms_choisis)][['ID_Site',"Nom", "Ouv_Matin", "Ferm_Matin", "Ouv_Aprem", "Ferm_Aprem"]]
                sites_finaux = pd.merge(edited_df, details_sites, on="Nom")
                st.session_state.sites_courants = sites_finaux

                st.info("Logique d'auto-remplissage à implémenter ici !")

            groupe = st.session_state.groupement_choisi
            noms_presents = st.session_state.sites_courants["Nom"].tolist()
        
            sites_dispos = st.session_state.site[
                (st.session_state.site["Groupement"] == groupe) &
                (~st.session_state.site["Nom"].isin(noms_presents)) 
            ]
        
            if sites_dispos.empty:
                st.info("Tous les sites du groupe sont inclus.")
            else:
                for _, site in sites_dispos.iterrows():
                    with st.container(border=True):
                        st.write(f"**{site['Nom']}**")
                        st.caption(f"{site['Horaires']}")
                        st.caption(f"Durée PEC : {site['Temps_PEC']} min")
                        if st.button(f"Ajouter à la journée", key=f"add_{site['ID_Site']}"):
                            edited_df["Temps_Total_Service"] = edited_df["Temps_PEC"] + edited_df["Maint_Prev"] + edited_df["Maint_Corr"]
                            noms_choisis = edited_df["Nom"].tolist()
                            details_sites = st.session_state.site[st.session_state.site["Nom"].isin(noms_choisis)][['ID_Site',"Nom", "Ouv_Matin", "Ferm_Matin", "Ouv_Aprem", "Ferm_Aprem"]]

                            sites_finaux = pd.merge(edited_df, details_sites, on="Nom")
                            st.session_state.sites_courants = sites_finaux

                            nouveau = pd.DataFrame([site])
                            nouveau["Temps_Total_Service"] = site["Temps_PEC"]
                            nouveau["Maint_Prev"] = 0
                            nouveau["Maint_Corr"] = 0
                            nouveau['ID_Site']=site['ID_Site']
                            st.session_state.sites_courants = pd.concat([st.session_state.sites_courants, nouveau], ignore_index=True)
                            st.rerun()

    # --- ÉTAPE 3 : SAUVEGARDE ---
    elif st.session_state.etape == 4:
        st.header("3. Validation et Sauvegarde")
    
        if st.session_state.resultat_tournee is not None:
            st.success("La tournée est optimisée et prête à être transmise.")
            st.dataframe(st.session_state.resultat_tournee, width='stretch')
        
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                if st.button("💾 Confirmer l'enregistrement"):
                    st.success("Tournée non enregistréepour le moment !")
            with col_f2:
                if st.button("🔄 Créer une autre tournée"):
                    st.session_state.etape = 1
                    st.session_state.sites_courants = pd.DataFrame()
                    st.session_state.resultat_tournee = None
                    st.rerun()
        else:
            st.warning("Aucune donnée à sauvegarder.")
            if st.button("Retour"):
                st.session_state.etape = 1
                st.rerun()

