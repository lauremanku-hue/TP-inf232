import os
import json
import pandas as pd
import plotly.express as px
import plotly.utils
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sklearn.linear_model import LinearRegression

# On désactive complètement la recherche de dossier d'instance
app = Flask(__name__, instance_path='/tmp', template_folder='../templates')
# On force l'instance path sur /tmp au cas où une extension le demande
app.instance_path = '/tmp'

# Configuration SQLite vers le dossier temporaire
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
    # Utilisation d'un moteur de connexion pour éviter les verrous SQLite
    with db.engine.connect() as conn:
        df_sante = pd.read_sql("SELECT * FROM sante_data", conn)
        df_secu = pd.read_sql("SELECT * FROM securite_routiere", conn)

    analyses = {}
    g_sante, i_sante = calculer_regression(df_sante, "Analyse Santé", "age", "valeur_principale", "#3366FF")
    g_secu, i_secu = calculer_regression(df_secu, "Vitesse par Lieu", "lieu", "vitesse_detectee", "#22CC22")
    
    analyses['sante'] = {'graph': g_sante, 'info': i_sante}
    analyses['secu'] = {'graph': g_secu, 'info': i_secu}

    return render_template('observatoire.html', analyses=analyses)
    
@app.route('/sante')
def page_sante():
    return render_template('menu_sante.html') # ou le nom exact de ton fichier

@app.route('/securite')
def page_securite():
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
    return redirect(url_for('accueil'))


