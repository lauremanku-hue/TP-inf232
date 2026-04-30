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
    __tablename__ = 'sante_data' # On force le nom de la table
    id = db.Column(db.Integer, primary_key=True)
    maladie = db.Column(db.String(50))
    patient_nom = db.Column(db.String(100))
    valeur_principale = db.Column(db.Float)
    age = db.Column(db.Integer)
    date = db.Column(db.DateTime, default=datetime.utcnow)

class SecuriteRoutiere(db.Model):
    __tablename__ = 'securite_routiere' # On force le nom de la table
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
    try:
        # On s'assure de bien lire les tables
        with db.engine.connect() as conn:
            df_sante = pd.read_sql("SELECT * FROM sante_data", conn)
            df_secu = pd.read_sql("SELECT * FROM securite_routiere", conn)

        # Calculs Sécurité (Stats de base)
        v_moyenne = df_secu['vitesse_detectee'].mean() if not df_secu.empty else 0
        v_max = df_secu['vitesse_detectee'].max() if not df_secu.empty else 0
        t_exces = (len(df_secu[df_secu['vitesse_detectee'] > 100]) / len(df_secu)) * 100 if not df_secu.empty else 0

        analyses = {}
        
        # --- FILTRAGE SANTÉ ---
        # On définit le mapping exact entre ce qui est écrit dans ta base et tes clés HTML
        # ATTENTION : Les noms à gauche doivent être EXACTEMENT ceux enregistrés via le formulaire
        mapping = [
            ('Diabète', 'diabete'), 
            ('Hypertension', 'hyper'), 
            ('Cancer', 'cancer')
        ]

        for m_db, m_key in mapping:
            if not df_sante.empty:
                # On filtre sur la colonne 'maladie' (nom défini dans ton modèle SanteData)
                df_filtre = df_sante[df_sante['maladie'] == m_db]
                
                if len(df_filtre) >= 2:
                    g, i = calculer_regression(df_filtre, m_db, "age", "valeur_principale", "#FF4444")
                    analyses[m_key] = {'graph': g, 'info': i}
                else:
                    analyses[m_key] = {'graph': None, 'info': None}
            else:
                analyses[m_key] = {'graph': None, 'info': None}

        # --- FILTRAGE SÉCURITÉ ---
        if not df_secu.empty and len(df_secu) >= 2:
            g_secu, i_secu = calculer_regression(df_secu, "Sécurité Routière", "lieu", "vitesse_detectee", "#22CC22")
            analyses['secu'] = {'graph': g_secu, 'info': i_secu}
        else:
            analyses['secu'] = {'graph': None, 'info': None}

        return render_template('observatoire.html', 
                               analyses=analyses, 
                               total=len(df_sante) + len(df_secu),
                               moyenne=round(v_moyenne, 1),
                               vitesse_max=v_max,
                               taux_exces=round(t_exces, 1))

    except Exception as e:
        print(f"ERREUR OBSERVATOIRE : {e}")
        return render_template('observatoire.html', analyses={}, total=0, moyenne=0, vitesse_max=0, taux_exces=0)
    
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
app.debug = True
if __name__ == "__main__":
    app.run()
