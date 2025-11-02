from flask import Flask, render_template, request, jsonify
import openai
import json
import random
from datetime import datetime
import re
import os

app = Flask(__name__)

# Configuration OpenAI
client = openai.OpenAI(api_key=os.environ.get('OPENAI_API_KEY', '6742012865:AAEPLQN_mianrxvljmdx6dStwb_iOS3rAQU'))

class GPTBetFoot:
    def __init__(self, bankroll=10000):
        self.bankroll = bankroll
        self.trades = []
        
    def parse_text_content(self, content):
        data = {
            'teams': re.findall(r'([A-Za-z\s]+)\s+vs\s+([A-Za-z\s]+)', content),
            'odds': re.findall(r'(\d+\.\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)', content),
            'xg': re.findall(r'xg_([a-z]+):\s*(\d+\.\d+)', content),
            'ranking': re.findall(r'classement_([a-z]+):\s*(\d+)', content),
            'form': re.findall(r'forme_([a-z]+):\s*([★☆]+)', content)
        }
        return data
    
    def calculate_fair_odds(self, data):
        try:
            # Extraire données
            xg_home = float(data['xg'][0][1]) if data['xg'] else 1.5
            xg_away = float(data['xg'][1][1]) if len(data['xg']) > 1 else 1.0
            
            rank_home = int(data['ranking'][0][1]) if data['ranking'] else 8
            rank_away = int(data['ranking'][1][1]) if len(data['ranking']) > 1 else 12
            
            form_home = data['form'][0][1].count('★') * 0.2 if data['form'] else 0.6
            form_away = data['form'][1][1].count('★') * 0.2 if len(data['form']) > 1 else 0.4
            
            # Modèle de calcul
            delta_xg = xg_home - xg_away
            delta_rank = (20 - rank_home) - (20 - rank_away)
            delta_form = form_home - form_away
            
            score = 0.3 * delta_xg + 0.2 * delta_rank + 0.1 * delta_form
            
            # Probabilités
            p_home = 1 / (1 + 2.71828 ** (-score))
            p_draw = 0.25 * (1 - abs(p_home - (1 - p_home)))
            p_away = 1 - p_home - p_draw
            
            # Normalisation
            total = p_home + p_draw + p_away
            p_home /= total
            p_draw /= total 
            p_away /= total
            
            # Cotes fair
            margin = 0.945
            fair_odds = {
                'home': round(1 / (p_home * margin), 2),
                'draw': round(1 / (p_draw * margin), 2),
                'away': round(1 / (p_away * margin), 2)
            }
            
            return {
                'probabilities': {
                    'home': round(p_home, 3),
                    'draw': round(p_draw, 3),
                    'away': round(p_away, 3)
                },
                'fair_odds': fair_odds,
                'confidence': min(0.95, abs(score) * 2)
            }
        except Exception as e:
            return {'error': str(e)}

    def analyze_match(self, text_content):
        data = self.parse_text_content(text_content)
        
        # Cotes bookmaker
        odds = data['odds'][0] if data['odds'] else ['2.10', '3.40', '3.60']
        book_odds = {
            'home': float(odds[0]),
            'draw': float(odds[1]),
            'away': float(odds[2])
        }
        
        # Calcul cotes fair
        fair_data = self.calculate_fair_odds(data)
        if 'error' in fair_data:
            return fair_data
        
        # Calcul edges
        edges = {}
        for market in ['home', 'draw', 'away']:
            if fair_data['fair_odds'][market] > book_odds[market]:
                edge = (fair_data['fair_odds'][market] - book_odds[market]) / book_odds[market]
                edges[market] = round(edge * 100, 2)
            else:
                edges[market] = 0.0
        
        # Meilleur edge
        if edges:
            best_market = max(edges.items(), key=lambda x: x[1])
            
            if best_market[1] >= 3.0:
                # Mise Kelly
                fair_prob = fair_data['probabilities'][best_market[0]]
                edge_decimal = best_market[1] / 100
                kelly_frac = edge_decimal / (book_odds[best_market[0]] - 1)
                kelly_frac = min(kelly_frac * 0.25, 0.05)
                stake = self.bankroll * kelly_frac
                
                team_names = data['teams'][0] if data['teams'] else ('Home', 'Away')
                
                recommendation = {
                    'match': f"{team_names[0]} vs {team_names[1]}",
                    'bet': best_market[0],
                    'odds': book_odds[best_market[0]],
                    'fair_odds': fair_data['fair_odds'][best_market[0]],
                    'edge': best_market[1],
                    'stake': round(stake, 2),
                    'stake_percent': round((stake / self.bankroll) * 100, 2),
                    'confidence': round(fair_data['confidence'], 2),
                    'probabilities': fair_data['probabilities'],
                    'action': 'BET'
                }
                
                self.simulate_trade(recommendation)
                return recommendation
        
        return {'action': 'NO_BET', 'max_edge': best_market[1] if edges else 0}

    def simulate_trade(self, recommendation):
        trade_id = f"TRADE_{len(self.trades) + 1:04d}"
        
        win = random.random() < 0.55
        
        if win:
            profit = recommendation['stake'] * (recommendation['odds'] - 1)
            result = 'WIN'
        else:
            profit = -recommendation['stake']
            result = 'LOSE'
        
        trade = {
            'id': trade_id,
            **recommendation,
            'result': result,
            'profit': round(profit, 2),
            'bankroll_before': self.bankroll
        }
        
        self.bankroll += profit
        trade['bankroll_after'] = round(self.bankroll, 2)
        self.trades.append(trade)
        return trade

# Instance globale
bot = GPTBetFoot()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        text_content = request.form.get('text_data', '')
        if not text_content:
            return jsonify({'error': 'Données texte requises'}), 400
        
        result = bot.analyze_match(text_content)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/trades')
def get_trades():
    return jsonify(bot.trades)

@app.route('/performance')
def get_performance():
    if not bot.trades:
        return jsonify({'total_trades': 0, 'win_rate': 0, 'bankroll': bot.bankroll})
    
    wins = sum(1 for trade in bot.trades if trade['result'] == 'WIN')
    total = len(bot.trades)
    win_rate = (wins / total) * 100
    
    return jsonify({
        'total_trades': total,
        'winning_trades': wins,
        'win_rate': round(win_rate, 1),
        'bankroll': round(bot.bankroll, 2)
    })

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy', 
        'service': 'GPT-Bet.Foot',
        'timestamp': datetime.now().isoformat(),
        'version': '2.0.0'
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
