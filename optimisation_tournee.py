import pandas as pd
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
import numpy as np

import transformer_horaire


def optimiser_tournee(sites_df, durations_df, horaire_tech):
    """Fonction qui optimise la tournée avec une exploration récursive pour la matinée"""

    if len(sites_df) <= 1:
        return None

    solution = None
    sites = sites_df.copy()
    durations = durations_df.copy()

    debut_tech, fin_tech = transformer_horaire.parser_plage_horaire(horaire_tech)

    if fin_tech < 780 or debut_tech > 780:
        return None # Cas sans pause midi, application simple du solveur ailleurs

    else:
        # --- GESTION DE LA MATINÉE ---
        _, id_site_ouvert_seulement_matin, id_site_ouvert_matin = ajuster_horaire_matin(horaire_tech, sites)

        sites_seulement_matin = sites[sites['ID_Site'].isin(id_site_ouvert_seulement_matin)]
        sites_candidats = sites[sites['ID_Site'].isin(id_site_ouvert_matin) & ~sites['ID_Site'].isin(id_site_ouvert_seulement_matin)]

        meilleur_score = (0,0,-float())
        meilleure_solution_matin = None
        meilleurs_sites_inclus = None
        memo = set() # Pour ne pas tester 2 fois la même combinaison de sites

        # FONCTION RÉCURSIVE D'EXPLORATION
        def explorer_combinaisons(sites_inclus, candidats_restants):
            nonlocal meilleur_score, meilleure_solution_matin, meilleurs_sites_inclus

            # Création d'une signature unique pour cette combinaison de sites
            signature = frozenset(sites_inclus['ID_Site'].tolist()) if not sites_inclus.empty else frozenset()
            if signature in memo:
                return # Déjà exploré
            memo.add(signature)

            # Si on n'a encore aucun site inclus, on lance la récursion sur les candidats un par un
            if sites_inclus.empty:
                for idx, row in candidats_restants.iterrows():
                    nouveaux_inclus = pd.concat([sites_inclus, row.to_frame().T], ignore_index=True)
                    nouveaux_candidats = candidats_restants.drop(idx)
                    explorer_combinaisons(nouveaux_inclus, nouveaux_candidats)
                return

            # Évaluer la configuration actuelle
            plage_horaire_reduit, _, _ = ajuster_horaire_matin(horaire_tech, sites_inclus)
            matrice_duration_reduite = reduire_taille(durations, sites_inclus)

            solution_test = appliquer_solveur(sites_inclus, matrice_duration_reduite, plage_horaire_reduit)

            # ÉLAGAGE : Si la combinaison actuelle est invalide (trop longue, etc.),
            # inutile d'essayer d'y ajouter d'autres sites. On coupe cette branche.
            if solution_test is None:
                return

            # Calcul du score si la solution est valide
            temps_tournee_str = solution_test[solution_test['Ordre'] == solution_test['Ordre'].max()]['Heure_Fin'].iloc[0]
            temps_tournee = transformer_horaire.heure_str_vers_minutes(temps_tournee_str)
            temps_service = sites_inclus['Temps_Total_Service'].sum()

            nb_sites = len(sites_inclus)

            #le score est un tuple, l'ordre dicte les priorités de comparaison 
            score =(temps_service,nb_sites,-temps_tournee )


            # Sauvegarde si c'est le meilleur score rencontré
            if score > meilleur_score:
                meilleur_score = score
                meilleure_solution_matin = solution_test
                meilleurs_sites_inclus = sites_inclus.copy()

            # RÉCURSION : On tente d'ajouter un site supplémentaire parmi les candidats restants
            for idx, row in candidats_restants.iterrows():
                nouveaux_inclus = pd.concat([sites_inclus, row.to_frame().T], ignore_index=True)
                nouveaux_candidats = candidats_restants.drop(idx)
                explorer_combinaisons(nouveaux_inclus, nouveaux_candidats)

        # Lancement de l'exploration récursive
        explorer_combinaisons(sites_seulement_matin, sites_candidats)

        # Vérification après exploration
        if meilleure_solution_matin is None and not sites_seulement_matin.empty:
            # Emploi du temps matinal trop chargé avec les sites obligatoires
            return None

        solution = meilleure_solution_matin
        current_site = meilleurs_sites_inclus if meilleurs_sites_inclus is not None else sites_seulement_matin

        # Si tous les sites ont été placés dans la matinée
        if solution is not None and sites[~sites['ID_Site'].isin(current_site['ID_Site'].tolist())].empty:
            return solution

        # --- GESTION DE L'APRÈS-MIDI ET DE LA PAUSE ---
        # (Le reste de ta logique originale pour l'après-midi reprend ici)

        sites_a_visiter = sites.copy()
        dernier_site_id = -1

        if solution is not None:
            heure_fin_matin = solution[solution['Ordre'] == solution['Ordre'].max()]['Heure_Fin'].iloc[0]
            sites_a_visiter = sites_a_visiter[~sites_a_visiter['ID_Site'].isin(solution['ID_Site'].tolist())].copy()
            dernier_site_id = solution[solution['Ordre'] == solution['Ordre'].max()]['ID_Site'].iloc[0]

            depot_depart_df = sites[sites['ID_Site'] == dernier_site_id].copy()
            depot_depart_df['Temps_Total_Service'] = 0

        else:
            debut_tech, _ = horaire_tech.split('-')
            heure_fin_matin = debut_tech

        duration_reduit = reduire_taille(durations, sites_a_visiter)
        duration_liste = dataFrame_en_matrice(durations)

        heure_fin_matin = transformer_horaire.heure_str_vers_minutes(heure_fin_matin)

        liste_solutions = []
        plage_horaire_reduit, _, _ = ajuster_horaire_matin(horaire_tech, sites_a_visiter)
        index = 0

        for indexrow, site in sites_a_visiter.iterrows():
            sites_test = sites_a_visiter.copy()
            trajet = 0

            if dernier_site_id > 0:
                trajet = duration_liste[dernier_site_id - 1][int(site['ID_Site']) - 1]
                heure_fin_matin = heure_fin_matin + trajet

            if heure_fin_matin > plage_horaire_reduit[index][1]:
                plage_horaire_aprem = ajuster_horaire_aprem(horaire_tech, sites_test, heure_fin_matin)
    
                service_avant_pause = 0

                duration_reduit = reduire_taille(durations, sites_a_visiter)
                duration_reduit_modif = duration_reduit.copy()

                for i in range(len(duration_reduit_modif)):
                    duration_reduit_modif[i][0] = 0
                    solution_local = appliquer_solveur_avec_depot(sites_a_visiter, duration_reduit_modif, plage_horaire_aprem, 0, service_avant_pause, heure_fin_matin)

            else: # On découpe le temps de travail avant et après la pause
                service_avant_pause = plage_horaire_reduit[index][1] - heure_fin_matin

                sites_test.loc[sites_test['ID_Site'] == site['ID_Site'], 'Temps_Total_Service'] = site['Temps_Total_Service'] - service_avant_pause

                plage_horaire_aprem = ajuster_horaire_aprem(horaire_tech, sites_test, heure_fin_matin + service_avant_pause)


                duration_reduit = reduire_taille(durations, sites_a_visiter)
                duration_reduit_modif = duration_reduit.copy()

                for i in range(len(duration_reduit_modif)):
                    duration_reduit_modif[i][index] = 0

                solution_local = appliquer_solveur_avec_depot(sites_a_visiter, duration_reduit_modif, plage_horaire_aprem, index, service_avant_pause, heure_fin_matin)

            if solution_local is not None:
                liste_solutions.append(solution_local)
                index += 1

        if liste_solutions:

            solution_a_garder = best_itineraire(liste_solutions)

            # Gestion du cas où on n'a pas de solution le matin (solution initiale est None)
            if solution is not None:
                solution_a_garder['Ordre'] = solution_a_garder['Ordre'] + solution['Ordre'].max()
                
                solution = pd.concat([solution, solution_a_garder], ignore_index=True)
            else:
                solution = solution_a_garder

        if index > 0 and solution is None:
            return None
        else:
            return solution




def best_itineraire (liste_itineraire) : 
    #la meilleure tournée est celle qui fini le plus tôt 
    #Car je pense qu'il est mieux de finir la journée plus tôt (donc ajouter un site si on gagne du temps)
    #de plus pour la poste, les sites qui ouvrent tot sont rares 

    meilleur_itineraire = None
    fin_meilleur_itineraire = 1439 #23h59
    for itineraire in liste_itineraire : 

        heure_fin_itineraire = transformer_horaire.heure_str_vers_minutes(itineraire[itineraire['Ordre'] == itineraire['Ordre'].to_list()[-1]]['Heure_Fin'].iloc[0])
        if heure_fin_itineraire < fin_meilleur_itineraire : 
            fin_meilleur_itineraire = heure_fin_itineraire
            meilleur_itineraire = itineraire

    return meilleur_itineraire


def dataFrame_en_matrice(df_matrice) : 
    matrice_liste = df_matrice.copy()
    matrice_liste = matrice_liste.drop('id',axis=1).to_numpy().tolist()


    for i in range (len(matrice_liste)) :
        for j in range (len(matrice_liste)) :
            current_value = matrice_liste[i][j]

            if isinstance(current_value, float) and current_value != current_value : 
                matrice_liste[i][j] =0
            try:
                matrice_liste[i][j] = round(float(matrice_liste[i][j])/60)
            except ValueError:
                # Cette partie ne devrait normalement pas être atteinte si les '' et NaN sont bien gérés,
                # mais elle sert de filet de sécurité pour tout autre type de donnée non numérique inattendu.
                matrice_liste[i][j] = 0

    
    return matrice_liste

def reduire_taille(durations, sites_df ) :
    """Fonvtion qui fait une copie de la matrice de durée et ne renvoie que les durée qui nous intéresse
    Entrée :
        -Matrice de duration
        -Liste de site
    Sortie :
        -Matrice réduite"""
    
    
    duration_liste  = durations.copy()
    duration_liste = duration_liste.drop('id',axis=1).to_numpy().tolist() 
    for i in range (len(duration_liste)) :
        for j in range (len(duration_liste)) :
            if duration_liste[i][j]=='' : 
                duration_liste[i][j] =0

    
    
    id_a_garder = sites_df['ID_Site'].tolist()



    index_a_garder = [int(num) for num in id_a_garder]

    duration_filtre = [
        [round(float(duration_liste[ligne - 1][colonne - 1])/60) for colonne in id_a_garder] for ligne in index_a_garder]
    


    return duration_filtre
    


def ajuster_horaire_matin(horaire_tech, sites_df) : 
    """Fonction qui transforme les horaires matinals des sites pour correspondre aux horaires du technicien
    Entrée : 
        - Horaire du technicien
        - Tableau des horaires des sites 
    Sortie : 
        -horaire format : [(**,**),...,(**,**)]
        
    Exemple : 
        -Site A : 09:00-11:30 / 14:00-18:00
        - Horaire technicien = 08:00-17:00 (on applique nous-même la pause du midi entre 11h45 et 12h30 avec une durée de 1h30)
        
        => 09:00-11:30"""
    
    debut_tech , fin_tech = transformer_horaire.parser_plage_horaire(horaire_tech)

    ouverture_matin = sites_df['Ouv_Matin'].tolist()
    fermeture_matin = sites_df['Ferm_Matin'].tolist()

    ouverture_aprem = sites_df['Ouv_Aprem'].tolist()

    ids = sites_df['ID_Site'].tolist()

    id_site_ouvert_seulement_matin = []
    id_site_ouvert_matin = []

    plage_horaire_matin = []
    for i in range(len(ouverture_matin)) : 
        if(ouverture_matin[i] < 660 and ouverture_matin[i] > 0) : 
            new_plage_matin = (max(debut_tech, ouverture_matin[i]), min(750, fermeture_matin[i]))
            id_site_ouvert_matin.append(ids[i])
            #max 12h40 pour la pause du midi
            if ouverture_aprem[i] == 0  :
                id_site_ouvert_seulement_matin.append(ids[i])
        else : 
            new_plage_matin = (0,0)

        plage_horaire_matin.append(new_plage_matin)

    
    return plage_horaire_matin, id_site_ouvert_seulement_matin,id_site_ouvert_matin



def ajuster_horaire_aprem(horaire_tech, sites_df,heure_fin_matin) : 
    """Fonction qui transforme les horaires matinals des sites pour correspondre aux horaires du technicien
    Entrée : 
        - Horaire du technicien
        - Tableau des horaires des sites 
    Sortie : 
        -horaire format : [(**,**),...,(**,**)]"""
    
    _ , fin_tech = transformer_horaire.parser_plage_horaire(horaire_tech)
    debut_tech = heure_fin_matin + 90
    if debut_tech> fin_tech : 
        plage_horaire_aprem = []
        for i in range(len(ouverture_matin)) :
            plage_horaire_aprem.append((0,0))
        return plage_horaire_aprem

    ouverture_matin = sites_df['Ouv_Matin'].tolist()
    fermeture_matin = sites_df['Ferm_Matin'].tolist()

    ouverture_aprem = sites_df['Ouv_Aprem'].tolist()
    fermeture_aprem = sites_df['Ferm_Aprem'].tolist()

    ids = sites_df['ID_Site'].tolist()


    id_site_ouvert_seulement_aprem = []


    plage_horaire_aprem = []
    for i in range(len(ouverture_matin)) : 

        if fermeture_matin[i] > 840 : 
            #si le site est ouvert en continu
            new_plage_aprem = (debut_tech,  min(fin_tech, fermeture_matin[i]))
            
        elif ouverture_matin[i] > 660 : 
            #si le site est ouvert que l'aprem
            new_plage_aprem = (max(debut_tech, ouverture_matin[i]), min(fin_tech, fermeture_matin[i]))
            id_site_ouvert_seulement_aprem.append(ids[i])

        elif ouverture_aprem[i] > 0 :
            new_plage_aprem = (max(debut_tech, ouverture_aprem[i]), min(fin_tech, fermeture_aprem[i]))

        
        else : 
            new_plage_aprem = (0,0)

        plage_horaire_aprem.append(new_plage_aprem)

    return plage_horaire_aprem




def appliquer_solveur(sites_df, duration_reduit,horaire) :
    """Foncion qui applique le solveur 
    Entrée : 
        -data avec ime_matrix, services_times, time_windows, num_vehicles,depot
    Sortie : 
        - ordre de visite des sites
    """
    if(len(duration_reduit)==0):
        return None
    
    
    temps_service_tot =  sites_df['Temps_Total_Service'].sum() 

    min_ouverture = 1439
    max_fermeture = 0

    for (ouverture, fermeture) in horaire : 
        if ouverture < min_ouverture : 
            min_ouverture = ouverture 
        if fermeture > max_fermeture :
            max_fermeture = fermeture

    approx_dispo_horaire = max_fermeture - min_ouverture

    if (temps_service_tot > approx_dispo_horaire) : 
        return None
    

    

    depot_virtuel_nom = "Dépôt Virtuel"
    depot_virtuel_id = 9999
    depot_virtuel_horaire = "00:00-23:55"
    depot_virtuel_row = pd.DataFrame([{
        'Nom': depot_virtuel_nom,
        'Horaires': depot_virtuel_horaire,
        'Temps_PEC' : 0,
        'Maint_Prev' :0 ,
        'Maint_Corr': 0,
        'Temps_Total_Service': 0,
        'Ouv_Matin': 0,
        'Ferm_Matin':1080,
        'Ouv_Aprem' : 0,
        'Ferm_Aprem' : 1080,
        'ID_Site': depot_virtuel_id,
        
    }])

    sites_df_avec_depot = pd.concat([depot_virtuel_row, sites_df], ignore_index=True)

    duration_reduit_avec_depot = duration_reduit.copy()
    for ligne in duration_reduit_avec_depot:
        ligne.insert(0, 0)
        
    longueur_ligne = len(duration_reduit_avec_depot[0])
    nouvelle_ligne_de_zeros = [0] * longueur_ligne
    duration_reduit_avec_depot.insert(0, nouvelle_ligne_de_zeros)

    horaire_avec_depot = horaire.copy()

    horaire_avec_depot.insert(0,(0,1080))

    
    data = {}

    data['time_matrix'] = duration_reduit_avec_depot
    
    data['num_vehicles'] = 1
    data['depot'] = 0

    data['time_service'] = sites_df_avec_depot['Temps_Total_Service'].tolist()
    data['time_windows'] = horaire_avec_depot
 
    manager = pywrapcp.RoutingIndexManager(len(data['time_matrix']), data['num_vehicles'], data['depot']) 
    routing = pywrapcp.RoutingModel(manager)
    
    def time_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        # On ne paie le trajet que si on ne sort pas/rentre pas au dépôt virtuel
        return data['time_matrix'][from_node][to_node] + data['time_service'][from_node]
    
    transit_callback_index = routing.RegisterTransitCallback(time_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    routing.AddDimension(
        transit_callback_index,
        60, # Temps d'attente autorisé (si on arrive trop tôt sur un site)
        1080, # Temps maximum cumulé (fin de journée)
        False,
        'Time'
    )
    time_dimension = routing.GetDimensionOrDie('Time')

    for location_idx, time_window in enumerate(data['time_windows']):
        index = manager.NodeToIndex(location_idx)
        time_dimension.CumulVar(index).SetRange(time_window[0], time_window[1]- data['time_service'][location_idx])

    
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search_parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search_parameters.time_limit.seconds = 2

    solution = routing.SolveWithParameters(search_parameters)
    
    if solution:
        itineraire = []
        index = routing.Start(0)
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            time_var = time_dimension.CumulVar(index)
            min_time = solution.Min(time_var)
            itineraire.append({
                "Ordre": len(itineraire) + 1,
                "Lieu": sites_df_avec_depot.iloc[node]["Nom"],
                "ID_Site" : int(sites_df_avec_depot.iloc[node]['ID_Site']),
                "Horaires": sites_df_avec_depot.iloc[node]["Horaires"],
                "Total Service": f"{data['time_service'][node]} min",
                "Heure_Debut": f"{min_time // 60:02d}:{min_time % 60:02d}",
                "Heure_Fin": f"{(min_time + data['time_service'][node]) // 60:02d}:{(min_time + data['time_service'][node]) % 60:02d}"
            })
            index = solution.Value(routing.NextVar(index))
        return pd.DataFrame(itineraire)
    else : 
        return None


def appliquer_solveur_avec_depot(sites_df, duration_reduit,horaire,index_depot, temps_service_avant_pause,heure_fin_matin) :
    """Foncion qui applique le solveur avec un point de depart donné
    Retourne la tournée de l'après-midi (sans le dépôt) et les infos de fin du dépôt
    """
    data = {}

    data['time_matrix'] = duration_reduit
    
    data['num_vehicles'] = 1
    data['depot'] = index_depot
    time_service = sites_df['Temps_Total_Service'].tolist()
    time_service[index_depot] = time_service[index_depot] - temps_service_avant_pause
    data['time_service'] = time_service

    data['time_windows'] = horaire
 
    manager = pywrapcp.RoutingIndexManager(len(data['time_matrix']), data['num_vehicles'], data['depot']) 
    routing = pywrapcp.RoutingModel(manager)
    
    def time_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        # On ne paie le trajet que si on ne sort pas/rentre pas au dépôt virtuel
        return data['time_matrix'][from_node][to_node] + data['time_service'][from_node]
    
    transit_callback_index = routing.RegisterTransitCallback(time_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    routing.AddDimension(
        transit_callback_index,
        60, # Temps d'attente autorisé (si on arrive trop tôt sur un site)
        1080, # Temps maximum cumulé (fin de journée)
        False,
        'Time'
    )
    time_dimension = routing.GetDimensionOrDie('Time')

    for location_idx, time_window in enumerate(data['time_windows']):
        index = manager.NodeToIndex(location_idx)
        if (time_window[0] >  time_window[1]- data['time_service'][location_idx]) :
            return None
        time_dimension.CumulVar(index).SetRange(time_window[0], time_window[1]- data['time_service'][location_idx])

    
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search_parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search_parameters.time_limit.seconds = 2

    solution = routing.SolveWithParameters(search_parameters)
    
    if solution:
        itineraire = []
        index = routing.Start(0)
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            time_var = time_dimension.CumulVar(index)
            min_time = solution.Min(time_var)
             
            if node !=index_depot :
                
        
                itineraire.append({
                    "Ordre": len(itineraire) + 1,
                    "Lieu": sites_df.iloc[node]["Nom"],
                    "ID_Site" : int(sites_df.iloc[node]['ID_Site']),
                    "Horaires": sites_df.iloc[node]["Horaires"],
                    "Total Service": f"{data['time_service'][node]} min",
                    "Heure_Debut": f"{min_time // 60:02d}:{min_time % 60:02d}",
                    "Heure_Fin": f"{(min_time + data['time_service'][node]) // 60:02d}:{(min_time + data['time_service'][node]) % 60:02d}"
                })

            else : 
            
                itineraire.append({
                    "Ordre": len(itineraire) + 1,
                    "Lieu": sites_df.iloc[node]["Nom"],
                    "ID_Site" : int(sites_df.iloc[node]['ID_Site']),
                    "Horaires": sites_df.iloc[node]["Horaires"],
                    "Total Service": f"{data['time_service'][node] + temps_service_avant_pause} min",
                    "Heure_Debut": f"{(heure_fin_matin) // 60:02d}:{(heure_fin_matin) % 60:02d}",
                    "Heure_Fin": f"{(min_time + data['time_service'][node]) // 60:02d}:{(min_time + data['time_service'][node]) % 60:02d}"
                })
            


            index = solution.Value(routing.NextVar(index))
        return pd.DataFrame(itineraire)
    else : 
        return None

