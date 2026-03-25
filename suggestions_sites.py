import pandas as pd 
import numpy as np 
import math

import transformer_horaire


def distance_euclidienne (point1, point2) :
    """fonction qui calcule la distance entre 2 points GPS en km"""
    lon1, lat1 = point1
    lon2, lat2 = point2

    delta_lat = (lat2 - lat1) * 111.132
    
    moy_lat_rad = math.radians((lat1 + lat2) / 2)
    delta_long = (lon2 - lon1) * 111.320 * math.cos(moy_lat_rad)
    
    return math.sqrt(delta_lat**2 + delta_long**2)



def calcul_milieu_segment(lat_depart, long_depart, lat_arrivee,long_arrivee) : 
    """Fonction qui prend en argument 2 point gps et renvoie le point gps au milieu et la longueur entre les 2 points"""
    
    longueur = round(distance_euclidienne((long_depart,lat_depart),(long_arrivee,lat_arrivee)),2)
    lat_milieu = round((lat_arrivee + lat_depart)/2,7)
    long_milieu = round((long_arrivee + long_depart)/2,7)
    
    return ( long_milieu, lat_milieu), longueur


def verif_point_dans_cercle(centre, rayon, point):
    """Vérifie si point appartient au cercle (centre rayon)
     = renvoie si la distance point-centre est plus petite que le rayon
      Retourne un booléen """
    rayon = max(rayon, 5)

    
    return distance_euclidienne(centre, point) < rayon

    

def calcul_temps_trajet_sup(id_point_depart, id_point_arrivee, id_point_a_ajouter, durations):
    """Calcul le temps de trajet supplémentaire si on ajoute le site 'id_point_a_ajouter au trajet
    Si id_point de depart ou id_point_arrivee = 0, ça veut dire qu'on ajoute ce site au début ou à la fin du trajet 
    Retourne un temps en minute"""

    duration_liste  = durations.copy()
    duration_liste = duration_liste.drop('id',axis=1).to_numpy().tolist() 

    for i in range (len(duration_liste)) :
        for j in range (len(duration_liste)) :
            if duration_liste[i][j]=='' : 
                duration_liste[i][j] =0


    if(id_point_depart == 0 and id_point_arrivee ==0) : 
        #il y a aucun site donc si on ajoute ce site, il n'y a pas de trajet supplémentaire
        trajet = 0

    elif(id_point_depart == 0):
        #le site qu'on veut ajouter est le site de départ
        trajet = float(duration_liste[id_point_a_ajouter - 1][id_point_arrivee - 1])

    elif(id_point_arrivee ==0):
        #le site qu'on veut ajouter est le site de fin de journée
        float(duration_liste[id_point_depart - 1][id_point_a_ajouter - 1])

    else : 
        #le site qu'on veut ajouter se situe au milieu de la tournée (on voit un site avant et un site après)
        trajet_sup = float(duration_liste[id_point_depart - 1][id_point_a_ajouter - 1]) + float(duration_liste[id_point_a_ajouter - 1][id_point_arrivee - 1])
        trajet_existant = float(duration_liste[id_point_depart - 1][id_point_arrivee - 1])

        trajet = round(trajet_sup - trajet_existant,2)

    return trajet


def sites_ouverts_tot_proches(id_point, durations,horaires) :
    """fonction qui renvoie les id des sites avec des horaires intéressants le matin à moins d'1h de route du point"""

    ids_ouverts_tot = horaires[horaires['Ouv_Matin'] <= 510]['ID_Site'].to_list()

    ids_ouverts_tot_proches = []


    duration_liste  = durations.copy()
    duration_liste = duration_liste.drop('id',axis=1).to_numpy().tolist() 

    for i in range (len(duration_liste)) :
        for j in range (len(duration_liste)) :
            if duration_liste[i][j]=='' : 
                duration_liste[i][j] =0

    for id in ids_ouverts_tot : 
        if float(duration_liste[id - 1 ][id_point - 1]) < 60 : 
            ids_ouverts_tot_proches.append(id)

    return ids_ouverts_tot_proches



def sites_fermes_tard_proches(id_point, durations,horaires) :
    """fonction qui renvoie les id des sites avec des horaires intéressants le soir à moins d'1h de route du point"""
    ids_fermes_tard = horaires[horaires['Ouv_Matin'] >= 990]['ID_Site'].to_list()

    ids_fermes_tard_proches = []


    duration_liste  = durations.copy()
    duration_liste = duration_liste.drop('id',axis=1).to_numpy().tolist() 

    for i in range (len(duration_liste)) :
        for j in range (len(duration_liste)) :
            if duration_liste[i][j]=='' : 
                duration_liste[i][j] =0

    for id in ids_fermes_tard : 
        if float(duration_liste[id_point - 1][id - 1]) < 60 : 
            ids_fermes_tard_proches.append(id)

    return ids_fermes_tard_proches


def choix_sites_a_suggerer(itineraire, site_df, durations, donnees_gps) :

    ids_a_suggerer = {}
    liste_id_itineraire = itineraire['ID_Site'].tolist()

    for i in range(len(liste_id_itineraire)) : 
        #On actualise les identifiants 
        #   de départ (= l'id précédent)
        #   d'arrivée (= l'id courant)
        #puis on fait une boucle pour tester quels sites vont être suggérés
        id_arrivee = liste_id_itineraire[i]
        nom_site_prec = []

        if(i == 0):
            id_depart = 0 
        else :
            id_depart = liste_id_itineraire[i - 1]
        
        if id_depart == 0 : 
            ids_a_suggerer_local = sites_ouverts_tot_proches(id_arrivee, durations,site_df)
            for id_local in ids_a_suggerer_local :
                if id_local not in itineraire['ID_Site'].to_list() : 
                    ids_a_suggerer[id_local] = (calcul_temps_trajet_sup(id_depart,id_arrivee,id_local,durations),"Début")
        
        else : 
            lat_depart = donnees_gps[donnees_gps['ID_Site']==id_depart]['latitude'].iloc[0]
            long_depart = donnees_gps[donnees_gps['ID_Site']==id_depart]['longitude'].iloc[0]

            lat_arrivee = donnees_gps[donnees_gps['ID_Site']==id_arrivee]['latitude'].iloc[0]
            long_arrivee = donnees_gps[donnees_gps['ID_Site']==id_arrivee]['longitude'].iloc[0]

            (centre, longueur) = calcul_milieu_segment(lat_depart, long_depart, lat_arrivee,long_arrivee)

            sites_a_tester = site_df[~site_df['ID_Site'].isin(itineraire['ID_Site'].to_list())]

            ids_a_tester = sites_a_tester['ID_Site'].to_list()

            for id_test in ids_a_tester :
                lat_test = donnees_gps[donnees_gps['ID_Site']==id_test]['latitude'].iloc[0]
                long_test = donnees_gps[donnees_gps['ID_Site']==id_test]['longitude'].iloc[0]

                if verif_point_dans_cercle(centre, longueur/2, (long_test, lat_test)) :
                    
                    if id_test not in ids_a_suggerer : 
                        ids_a_suggerer[id_test] = (calcul_temps_trajet_sup(id_depart,id_arrivee,id_test,durations),site_df[site_df['ID_Site']==id_depart]['Nom'].iloc[0])
                    else : 
                        temps, _ = ids_a_suggerer[id_test]
                        if(temps > calcul_temps_trajet_sup(id_depart,id_arrivee,id_test,durations)) : 
                            ids_a_suggerer[id_test] = (calcul_temps_trajet_sup(id_depart,id_arrivee,id_test,durations),site_df[site_df['ID_Site']==id_depart]['Nom'].iloc[0])

    if(len(liste_id_itineraire)> 1) :    
        ids_a_suggerer_local = sites_fermes_tard_proches(id_arrivee, durations,site_df)
        for id_local in ids_a_suggerer_local :
            if id_local not in ids_a_suggerer : 
                ids_a_suggerer[id_local] = calcul_temps_trajet_sup(id_depart,id_arrivee,id_local,durations)
            else : 
                ids_a_suggerer[id_local] = min(ids_a_suggerer[id_local],calcul_temps_trajet_sup(id_depart,id_arrivee,id_local,durations))
    
    liste_ids_a_suggerer = []
    temps_trajet_sup = []
    for cle, valeur in ids_a_suggerer.items():
        liste_ids_a_suggerer.append(cle)
        temps, nom = valeur 
        temps_trajet_sup.append(temps)
        nom_site_prec.append(nom)
        
    

    return ids_a_suggerer, temps_trajet_sup,nom_site_prec


