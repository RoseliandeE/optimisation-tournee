import pandas as pd
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
import numpy as np

import transformer_horaire



def optimiser_tournee(sites_df, durations_df,horaire_tech):
    """Fonction qui optimise la tournée
    Logique : 
        - Si le technicien est présent que le matin ou l'aprem, on applique le solveur direct 
        - Sinon 
            -On applique le solveur sur les sites ouverts seulement le matin
            -On ajoute le plus de site possible pour "combler" la matinée
            -On fait une boucle sur tous les sites restants
                -Ce site sera celui de la pause du midi (on va fractionner son temps de travail ou trajet) 
                et on applique le solveur sur le reste des sites pour l'après midi
                -On garde la meilleure solution """
    
    if len(sites_df) <= 1:
        #s'il n'y a qu'un seul site, on ne fait pas de calcul de tournée
        return None
    
    solution = None
    
    #on travaille sur des copies au cas ou 
    sites = sites_df.copy()
    durations = durations_df.copy()

    #horaire du technicien sous forme de tuple de minutes ex : 8h-17h = (480,1020)
    debut_tech, fin_tech = transformer_horaire.parser_plage_horaire(horaire_tech)
    print('---------------------------------------------------')
    print('debut optimisation')
    print('---------------------------------------------------')


    if fin_tech < 780  : #si le tech fini avant 13h
        return None #appliquer le solveur "simplement" car on a qu'une plage horaire

    elif debut_tech > 780 : #Si le tech commence après 13h
        return None #idem, on applique le solveur "simplement"
    
    else : 
        # Cas d'une journée 'normale' avec pause déjeuner

        # Filtrer les sites qui sont ouverts SEULEMENT le matin
        _, id_site_ouvert_seulement_matin, id_site_ouvert_matin = ajuster_horaire_matin(horaire_tech, sites)
        current_site = sites[sites['ID_Site'].isin(id_site_ouvert_seulement_matin)] #sites ouvert seulement le matin

        # Réduire les données pour le solveur du matin (sites ouverts seulement le matin)
        # On ajuste les plages horaires uniquement pour ces sites
        plage_horaire_reduit, _,_= ajuster_horaire_matin(horaire_tech, current_site)
        matrice_duration_reduite = reduire_taille(durations,current_site)

        

        #Solution exacte pour les sites ouverts seulement le matin 
        if not current_site.empty:
            solution = appliquer_solveur(current_site, matrice_duration_reduite, plage_horaire_reduit)
        
    
        if (solution is None and not current_site.empty) : 
            # Si pas de solution alors qu'il y a des sites ouverts seulement le matin
            # = Emploi du temps matinal trop chargé / contraintes non respectées
            return None
        


        if(sites[~sites['ID_Site'].isin(current_site['ID_Site'].to_list())].empty) : 
            #si il n'y a plus de site dans la liste
            return solution
        
        
        else : 
        
            site_ouvert_matin = sites[sites['ID_Site'].isin(id_site_ouvert_matin)] #tous les sites ouverts le matin 

            if solution is not None : 
                #Si il y a une solution pour faire une tournée avec les sites ouverts seulement le matin 
                site_ouvert_matin_aprem = site_ouvert_matin[~site_ouvert_matin['ID_Site'].isin(solution['ID_Site'].to_list())] #site ouvert matin ET après midi 
                temps_tournee = solution[solution['Ordre']==max(solution['Ordre'].to_list())]['Heure_Fin'].iloc(0)
            
            else : #il n'y a aucun site ouvert seulement le matin
                site_ouvert_matin_aprem = site_ouvert_matin.copy()
                temps_tournee=0


            prec_score_gain = -1 #le temps de service gagné à l'étape n-1 (permet d'arreter la boucle si pas de gain )
            current_score_gain = 0 #le temps de service gagné à l'étape n 
            id_a_ajouter = 0 #l'id du site à ajouter

            solution_a_garder = None


            #boucle pour ajouter tous les sites possibles à la tournée du matin 
            while current_score_gain - prec_score_gain > 0 : #si le temps 'gain' n'a pas changé, c'est qu'on a ajouté le max de site
                #cette boucle nest pas optimal car on pourrait avoir une situation comme 
                # - 4h libre
                # -  un site avec 2h de temps de service pour 1h de trajet = 1h de trajet et 2h de travail 
                # 2 sites très proches entre eux (=10min de trajet) avec 1h25 chacun de service et 1h de trajet pour y aller = 1h10 de trajet et 2h50 de travail
                #on va choisir le premier avec site alors que la 2eme config est meilleure 

                prec_score_gain = current_score_gain 
                id_a_ajouter = 0 #l'identifiant du site à ajouter à la tournée
                solution_a_garder = None

                for index_row, row_series in site_ouvert_matin_aprem.iterrows():

                    sites_test = current_site.copy()
                    row_df = row_series.to_frame().T #on récupère la ligne et on la transfrome en dataFrame
                    row_df.columns = current_site.columns 
                    sites_test = pd.concat([sites_test, row_df], ignore_index=True) #pour ajouter la ligne au dataFrame de test

                    plage_horaire_reduit, _,_ = ajuster_horaire_matin(horaire_tech, sites_test)
                    matrice_duration_reduite = reduire_taille(durations,sites_test)


                    new_solution = appliquer_solveur(sites_test,matrice_duration_reduite, plage_horaire_reduit)
                    

                    if new_solution is not None : 
                        temps_tournee = new_solution[new_solution['Ordre']==max(new_solution['Ordre'].to_list())]['Heure_Fin'].iloc[0] 
                        #on prend l'heure de fin de service du dernier site = l'heure de la fin de la tournée
                        temps_tournee = transformer_horaire.heure_str_vers_minutes(temps_tournee)
                        temps_service = sites_test['Temps_Total_Service'].sum()


                        if temps_service/temps_tournee > current_score_gain : 
                            #on utilise un rapport entre le temps de tournée 
                            current_score_gain = temps_service/temps_tournee
                            id_a_ajouter = row_df['ID_Site'].iloc[0]

                            solution_a_garder = new_solution
                
                if solution_a_garder is not None : 
                    solution = solution_a_garder
                    ligne_a_ajouter_df = site_ouvert_matin_aprem[site_ouvert_matin_aprem['ID_Site'] == id_a_ajouter]
                    for indexrow, ligne in current_site.iterrows():
                        if(ligne['ID_Site'] in ligne_a_ajouter_df) :
                            ligne['Heure_Fin'] = ligne_a_ajouter_df[ligne_a_ajouter_df['ID_Site']==ligne['ID_Site']]['Heure_Fin']
                            ligne['Temps_Total_Service'] = ligne_a_ajouter_df[ligne_a_ajouter_df['ID_Site']==ligne['ID_Site']]['Temps_Total_Service'] + ligne['Temps_Total_Service']
                            ligne_a_ajouter_df = ligne_a_ajouter_df[~ligne_a_ajouter_df['ID_Site']==ligne['ID_Site']]
                    current_site_maj = pd.concat([current_site, ligne_a_ajouter_df], ignore_index=True)
                    current_site = current_site_maj
                    site_ouvert_matin_aprem = site_ouvert_matin_aprem[~site_ouvert_matin_aprem['ID_Site'].isin(current_site['ID_Site'].to_list())]


                    if(sites[~sites['ID_Site'].isin(current_site['ID_Site'].to_list())].empty) : 
                        return solution
                        
            
            
            sites_a_visiter = sites.copy()

            dernier_site_id = -1
            

            if solution is not None :
                heure_fin_matin = solution[solution['Ordre']==max(solution['Ordre'].to_list())]['Heure_Fin'].iloc[0]
                sites_a_visiter = sites_a_visiter[~sites_a_visiter['ID_Site'].isin(solution['ID_Site'].to_list())].copy()
                dernier_site_id = solution[solution['Ordre'] == solution['Ordre'].to_list()[-1]]['ID_Site'].iloc[0]

                depot_depart_df = sites[sites['ID_Site'] == dernier_site_id].copy()
                depot_depart_df['Temps_Total_Service'] = 0 

                


            else : 
                debut_tech, _ = horaire_tech.split('-')
                heure_fin_matin = debut_tech
                

            duration_reduit = reduire_taille(durations,sites_a_visiter)
            duration_liste = dataFrame_en_matrice(durations)

            heure_fin_matin = transformer_horaire.heure_str_vers_minutes(heure_fin_matin)

            liste_solutions = []
            plage_horaire_reduit,_,_ = ajuster_horaire_matin(horaire_tech,sites_a_visiter)
            index = 0 


            for indexrow,site in sites_a_visiter.iterrows() : 
                
                sites_test = sites_a_visiter.copy()
                trajet = 0 


                if dernier_site_id > 0 : 
                    #si on a déjà vu au moins un site avant 
                    trajet = duration_liste[dernier_site_id -1][int(site['ID_Site'])-1]
                    heure_fin_matin = heure_fin_matin + trajet


                if heure_fin_matin > plage_horaire_reduit[index][1] :
                    #si après le trajet on n'est plus sur la plage horaire du matin
                    #le depot est le site après le trajet 



                    plage_horaire_aprem = ajuster_horaire_aprem(horaire_tech,sites_test,heure_fin_matin)
                    service_avant_pause = 0 

                    #sites_a_visiter = pd.concat([depot_depart_df,sites_a_visiter],ignore_index=True)
                    duration_reduit = reduire_taille(durations,sites_a_visiter)
                    duration_reduit_modif = duration_reduit.copy()


                    for i in range(len(duration_reduit_modif)) : 
                        duration_reduit_modif[i][0] = 0 
                    solution_local = appliquer_solveur_avec_depot(sites_a_visiter,duration_reduit_modif, plage_horaire_aprem,0,service_avant_pause,heure_fin_matin)
                

                else : #on découpe le temps de travail avant et après la pause 
                    service_avant_pause = plage_horaire_reduit[index][1] - heure_fin_matin #temps de travail avant la pause 

                    
                    sites_test[sites_test['ID_Site']==site['ID_Site']]['Temps_Total_Service'] = site['Temps_Total_Service'] - service_avant_pause #temps restant de travail 
                    
                    plage_horaire_aprem = ajuster_horaire_aprem(horaire_tech,sites_test,heure_fin_matin + service_avant_pause)
                    duration_reduit = reduire_taille(durations,sites_a_visiter)
                    duration_reduit_modif = duration_reduit.copy()

                    for i in range(len(duration_reduit_modif)) : 
                        duration_reduit_modif[i][index] = 0 

                    solution_local = appliquer_solveur_avec_depot(sites_a_visiter,duration_reduit_modif, plage_horaire_aprem,index,service_avant_pause,heure_fin_matin)


                if solution_local is not None : 
                    print(solution_local)
                    liste_solutions.append(solution_local)
                index +=1
            
            if liste_solutions != [] : 
                solution_a_garder = best_itineraire(liste_solutions)
                solution_a_garder['Ordre'] = solution_a_garder['Ordre'] + max(solution['Ordre'].to_list())
                solution = pd.concat([solution, solution_a_garder], ignore_index=True)

            if index > 0 and solution is None : 
                return None
            else : 
                return solution 


def best_itineraire (liste_itineraire) : 
    #la meilleure tournée est celle qui fini le plus tôt 
    #Car je pense qu'il est mieux de finir la journée plus tôt (donc ajouter un site si on gagne du temps)
    #de plus pour la poste, les sites qui ouvrent tot sont rares 

    print("LISTE SOLUTIONS ")

    print(liste_itineraire)

    meilleur_itineraire = None
    fin_meilleur_itineraire = 1439 #23h59
    for itineraire in liste_itineraire : 

        print(itineraire)
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
                print(f"Attention : La valeur '{matrice_liste[i][j]}' à la position [{i}][{j}] n'a pas pu être convertie en nombre. Elle sera traitée comme 0.")
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
        print('((((((((((((((((((((((((((()))))))))))))))))))))))))))')

        if fermeture_matin[i] > 840 : 
            #si le site est ouvert en continu
            new_plage_aprem = (debut_tech,  min(fin_tech, fermeture_matin[i]))
            
        elif ouverture_matin[i] > 660 : 
            #si le site est ouvert que l'aprem
            new_plage_aprem = (max(debut_tech, ouverture_matin[i]), min(fin_tech, fermeture_matin[i]))
            id_site_ouvert_seulement_aprem.append(ids[i])

        elif ouverture_aprem[i] > 0 :
            
            new_plage_aprem = (max(debut_tech, ouverture_aprem[i]), min(fin_tech, fermeture_aprem[i]))
            print(debut_tech)
            print(max(debut_tech, ouverture_aprem[i]))

        
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

    print("appliquer_solveur : ")

    print(data)

    

    
 
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
                "Heure_Arrivee": f"{min_time // 60:02d}:{min_time % 60:02d}",
                "Heure_Fin": f"{(min_time + data['time_service'][node]) // 60:02d}:{(min_time + data['time_service'][node]) % 60:02d}"
            })
            index = solution.Value(routing.NextVar(index))
            print(itineraire)
        return pd.DataFrame(itineraire)
    else : 
        print("Aucune solution")
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

    print("appliquer solveur avec depot")
    print(data)

    print(heure_fin_matin)
    print(horaire)
 
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
                    "Heure_Arrivee": f"{min_time // 60:02d}:{min_time % 60:02d}",
                    "Heure_Fin": f"{(min_time + data['time_service'][node]) // 60:02d}:{(min_time + data['time_service'][node]) % 60:02d}"
                })

            else : 
            
                itineraire.append({
                    "Ordre": len(itineraire) + 1,
                    "Lieu": sites_df.iloc[node]["Nom"],
                    "ID_Site" : int(sites_df.iloc[node]['ID_Site']),
                    "Horaires": sites_df.iloc[node]["Horaires"],
                    "Total Service": f"{data['time_service'][node] + temps_service_avant_pause} min",
                    "Heure_Arrivee": f"{(heure_fin_matin  - temps_service_avant_pause) // 60:02d}:{(heure_fin_matin - temps_service_avant_pause) % 60:02d}",
                    "Heure_Fin": f"{(min_time + data['time_service'][node]) // 60:02d}:{(min_time + data['time_service'][node]) % 60:02d}"
                })
            


            index = solution.Value(routing.NextVar(index))
            print(itineraire)
        return pd.DataFrame(itineraire)
    else : 
        print("Aucune solution")
        return None

