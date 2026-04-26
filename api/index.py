import pandas as pd
import plotly.express as px
import plotly.utils
import json
from sklearn.linear_model import LinearRegression
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os

app = Flask(__name__)

# --- CONFIGURATION VERCEL / SQLITE ---
if os.environ.get('VERCEL'):
    # Utilisation du dossier /tmp pour éviter l'erreur "Read-only file system"
    db_path = '/tmp/test.db'
else:
    db_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'laure_collecte.db')

app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['FLASK_SQLALCHEMY_INSTANCE_SYSTEM'] = False 
app.secret_key = 'une_cle_secrete_inf232'

db = SQLAlchemy(app)

# --- MODÈLES DE DONNÉES ---
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

# --- LOGIQUE DE CALCUL ---
def calculer_regression(df, titre, label_x, label_y, couleur):
    if df.empty:
        return None, None
    
    df[label_y] = pd.to_numeric(df[label_y], errors='coerce')
    df = df.dropna(subset=[label_y])

    # --- SÉCURITÉ : ANALYSE DESCRIPTIVE ---
    if "Sécurité" in titre:
        vitesse_moyenne = df[label_y].mean()
        vitesse_max = df[label_y].max()
        ecart_type = df[label_y].std()
        taux_exces = (len(df[df[label_y] > 110]) / len(df)) * 100 if len(df) > 0 else 0
        
        df_plot = df.groupby('lieu')[label_y].mean().reset_index()
        fig = px.bar(df_plot, x='lieu', y=label_y, title=titre, color_discrete_sequence=[couleur])

        stats = {
            'type': 'descriptif',
            'moyenne': round(vitesse_moyenne, 1),
            'max': vitesse_max,
            'ecart_type': round(ecart_type, 2) if not pd.isna(ecart_type) else 0,
            'taux_exces': round(taux_exces, 1),
            'total': len(df),
            'pente': round(vitesse_moyenne / 120, 2)
        }

    # --- SANTÉ : MODÈLE ET ESTIMATION ---
    else:
        df[label_x] = pd.to_numeric(df[label_x], errors='coerce')
        df = df.dropna(subset=[label_x])

        if len(df) < 2: return None, {"type": "erreur", "msg": "Pas assez de données"}

        model = LinearRegression()
        X = df[[label_x]].values
        y = df[label_y].values
        model.fit(X, y)

        age_pred = int(df[label_x].max() + 5)
        val_pred = model.predict([[age_pred]])[0]

        df['classe_age'] = (df[label_x] // 10 * 10).astype(str) + "-" + (df[label_x] // 10 * 10 + 9).astype(str)
        df_plot = df.groupby('classe_age')[label_y].mean().reset_index()

        fig = px.bar(df_plot, x='classe_age', y=label_y, title=f"Répartition par âge : {titre}",
                     color_discrete_sequence=[couleur], text_auto='.1f')

        stats = {
            'type': 'modele',
            'pente': round(model.coef_[0], 3),
            'equation': f"y = {model.coef_[0]:.2f}x + {model.intercept_:.2f}",
            'pred_age': age_pred,
            'pred_val': round(val_pred, 2),
            'r2': round(model.score(X, y), 2)
        }

    fig.update_layout(template="plotly_white", height=450)
    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder), stats

# --- ROUTES ---

@app.route('/')
def accueil():
    return render_template('accueil.html')

@app.route('/observatoire')
def observatoire():
    conn = db.engine.connect()
    df_sante = pd.read_sql("SELECT * FROM sante_data", conn)
    df_secu = pd.read_sql("SELECT * FROM securite_routiere", conn)
    conn.close()

    analyses = {}
    g_sante, i_sante = calculer_regression(df_sante, "Suivi Santé", "age", "valeur_principale", "#3366FF")
    analyses['sante'] = {'graph': g_sante, 'info': i_sante}
    
    g_secu, i_secu = calculer_regression(df_secu, "Sécurité Routière", "lieu", "vitesse_detectee", "#22CC22")
    analyses['secu'] = {'graph': g_secu, 'info': i_secu}

    # Calcul des stats globales pour l'affichage
    v_moyenne = df_secu['vitesse_detectee'].mean() if not df_secu.empty else 0
    v_max = df_secu['vitesse_detectee'].max() if not df_secu.empty else 0
    taux_exces = (len(df_secu[df_secu['vitesse_detectee'] > 110]) / len(df_secu)) * 100 if not df_secu.empty else 0

    return render_template('observatoire.html', 
                           analyses=analyses, 
                           total=len(df_sante)+len(df_secu),
                           moyenne=round(v_moyenne, 1),
                           vitesse_max=v_max,
                           taux_exces=round(taux_exces, 1))

@app.route('/form_securite')
def page_form_securite():
    return render_template('form_securite.html')

@app.route('/sante')
def menu_sante():
    return render_template('menu_sante.html')

@app.route('/form_sante')
def page_form_sante():
    maladie_choisie = request.args.get('maladie', 'Général')
    return render_template('form_sante.html', maladie=maladie_choisie)

@app.route('/enregistrer_securite', methods=['POST'])
def enregistrer_securite():
    try:
        nouvel_enregistrement = SecuriteRoutiere(
            lieu=request.form.get('lieu'),
            type_infraction=request.form.get('type_infraction'),
            gravite_estimee=float(request.form.get('gravite', 0)),
            vitesse_detectee=int(request.form.get('vitesse', 0))
        )
        db.session.add(nouvel_enregistrement)
        db.session.commit()
        flash(f'✅ Succès ! Infraction à {nouvel_enregistrement.lieu} enregistrée.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Erreur : {e}', 'danger')
    return redirect(url_for('page_form_securite'))

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
        flash(f'✅ Succès : Le cas de {nouvel_enregistrement.maladie} a été enregistré !', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Erreur : {e}', 'danger')
    return redirect(url_for('page_form_sante', maladie=request.form.get('maladie')))

if __name__ == '__main__':
    app.run(debug=True)
