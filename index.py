import os
import json
import pandas as pd
import plotly.express as px
import plotly.utils
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sklearn.linear_model import LinearRegression

# --- AJOUTE CES DEUX LIGNES ICI ---
base_dir = os.path.dirname(os.path.abspath(__file__))

# On utilise base_dir qu'on vient de définir
app = Flask(__name__, 
            instance_path='/tmp', 
            template_folder=os.path.join(base_dir, 'templates'))

# Le reste de ta configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/laure_data.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'une_cle_secrete_inf232'

db = SQLAlchemy(app)


# --- MODÈLES ---
class SanteData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    maladie = db.Column(db.String(50))
    patient_nom = db.Column(db.String(100))
    valeur_principale = db.Column(db.Float)
    age = db.Column(db.Integer)
    date = db.Column(db.DateTime, default=datetime.utcnow)

class SecuriteRoutiere(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lieu = db.Column(db.String(200))
    type_infraction = db.Column(db.String(100))
    gravite_estimee = db.Column(db.Float)
    vitesse_detectee = db.Column(db.Integer)
    date = db.Column(db.DateTime, default=datetime.utcnow)

# Création des tables
with app.app_context():
    db.create_all()

# --- FONCTION DE CALCUL ---
def calculer_regression(df, titre, label_x, label_y, couleur):
    if df.empty or len(df) < 1:
        return None, None
    
    # Sécurité Routière (Statistiques descriptives)
    if "Sécurité" in titre:
        vitesse_moyenne = df[label_y].mean()
        stats = {
            'type': 'descriptif',
            'moyenne': round(vitesse_moyenne, 1),
            'max': df[label_y].max(),
            'total': len(df)
        }
        fig = px.bar(df, x=label_x, y=label_y, title=titre, color_discrete_sequence=[couleur])
    
    # Santé (Régression Linéaire)
    else:
        if len(df) < 2: return None, None
        model = LinearRegression()
        X = df[[label_x]].values
        y = df[label_y].values
        model.fit(X, y)
        stats = {
            'type': 'modele',
            'equation': f"y = {model.coef_[0]:.2f}x + {model.intercept_:.2f}",
            'r2': round(model.score(X, y), 2)
        }
        fig = px.scatter(df, x=label_x, y=label_y, title=titre, trendline="ols", color_discrete_sequence=[couleur])

    fig.update_layout(template="plotly_white", height=400)
    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder), stats

# --- ROUTES ---
@app.route('/')
def accueil():
    return render_template('accueil.html')

@app.route('/observatoire')
def observatoire():
    donnees = MaTable.query.all()
    if not donnees:
        flash("Aucune donnée disponible pour le moment.")
        return redirect(url_for('observatoire'))
    # Utilisation d'un moteur de connexion pour éviter les verrous SQLite
    with db.engine.connect() as conn:
        df_sante = pd.read_sql("SELECT * FROM sante_data", conn)
        df_secu = pd.read_sql("SELECT * FROM securite_routiere", conn)

    analyses = {}

    # --- PARTIE SANTÉ : Séparation par maladie ---
    if not df_sante.empty:
        # On récupère la liste des maladies uniques (ex: 'diabete', 'hypertension')
        maladies = df_sante['nom_maladie'].unique() 
        
        for mal in maladies:
            # 1. On filtre avec le nom exact (ex: "Diabète")
            df_filtre = df_sante[df_sante['nom_maladie'] == mal]
            
            # 2. On nettoie le nom pour créer une clé compatible avec le HTML
            # (Ex: "Diabète" devient "diabete")
            cle_html = mal.lower().replace('è', 'e').replace('é', 'e').strip()
            
            # 3. On calcule la régression
            graph, info = calculer_regression(
                df_filtre, 
                f"Analyse {mal.capitalize()}", 
                "age", 
                "valeur_principale", 
                "#3366FF"
            )
            
            # 4. On enregistre avec la clé propre
            analyses[cle_html] = {'graph': graph, 'info': info}

    # --- PARTIE SÉCURITÉ ---
    if not df_secu.empty:
        g_secu, i_secu = calculer_regression(
            df_secu, 
            "Vitesse par Lieu", 
            "lieu", 
            "vitesse_detectee", 
            "#22CC22"
        )
        analyses['secu'] = {'graph': g_secu, 'info': i_secu}
    return render_template('observatoire.html', analyses=analyses)
    
@app.route('/sante')
def page_sante():
    return render_template('menu_sante.html') # ou le nom exact de ton fichier

@app.route('/form_securite')
def form_securite():
    return render_template('form_securite.html')
    
@app.route('/form_sante')
def page_form_sante():
    maladie = request.args.get('maladie', 'Général')
    return render_template('form_sante.html', maladie=maladie)
    
@app.route('/enregistrer_sante', methods=['POST'])
def enregistrer_sante():
    try:
        nouvel_enregistrement = SanteData(
            maladie=request.form.get('maladie'),
            patient_nom=request.form.get('patient_nom'),
            valeur_principale=float(request.form.get('valeur_principale', 0)),
            age=int(request.form.get('age', 0))
        )
        db.session.add(nouvel_enregistrement)
        db.session.commit()
        flash(f'✅ Cas de {nouvel_enregistrement.maladie} enregistré !', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Erreur : {e}', 'danger')
    return redirect(url_for('page_form_sante', maladie=request.form.get('maladie')))   

@app.route('/enregistrer_securite', methods=['POST'])
def enregistrer_securite():
    try:
        secu = SecuriteRoutiere(
            lieu=request.form.get('lieu'),
            type_infraction=request.form.get('type_infraction'),
            gravite_estimee=float(request.form.get('gravite', 0)),
            vitesse_detectee=int(request.form.get('vitesse', 0))
        )
        db.session.add(secu)
        db.session.commit()
        flash('Données enregistrées !', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erreur : {e}', 'danger')
    return redirect(url_for('form_securite'))

if __name__ == "__main__":
    app.run()
app.debug = True
