# -*- coding: utf-8 -*-

# Copyright (c) 2022-2023 tecnovert
# Distributed under the MIT software license, see the accompanying
# file LICENSE or http://www.opensource.org/licenses/mit-license.php.

import traceback

from .util import (
    get_data_entry,
    have_data_entry,
    checkAddressesOwned,
)
from basicswap.util import (
    ensure,
    format_timestamp,
)
from basicswap.chainparams import (
    Coins,
    getCoinIdFromTicker,
)


def format_wallet_data(swap_client, ci, w):
    wf = {
        'name': ci.coin_name(),
        'version': w.get('version', '?'),
        'ticker': ci.ticker_mainnet(),
        'cid': str(int(ci.coin_type())),
        'balance': w.get('balance', '?'),
        'blocks': w.get('blocks', '?'),
        'synced': w.get('synced', '?'),
        'expected_seed': w.get('expected_seed', '?'),
        'encrypted': w.get('encrypted', '?'),
        'locked': w.get('locked', '?'),
        'updating': w.get('updating', '?'),
        'havedata': True,
    }

    if w.get('bootstrapping', False) is True:
        wf['bootstrapping'] = True
    if 'known_block_count' in w:
        wf['known_block_count'] = w['known_block_count']

    if 'balance' in w and 'unconfirmed' in w:
        wf['balance_all'] = float(w['balance']) + float(w['unconfirmed'])
    if 'lastupdated' in w:
        wf['lastupdated'] = format_timestamp(w['lastupdated'])
    if 'unconfirmed' in w and float(w['unconfirmed']) > 0.0:
        wf['unconfirmed'] = w['unconfirmed']

    if ci.coin_type() == Coins.PART:
        wf['stealth_address'] = w.get('stealth_address', '?')
        wf['blind_balance'] = "{:.8f}".format(float(w['blind_balance']))
        if 'blind_unconfirmed' in w and float(w['blind_unconfirmed']) > 0.0:
            wf['blind_unconfirmed'] = w['blind_unconfirmed']
        wf['anon_balance'] = w.get('anon_balance', '?')
        if 'anon_pending' in w and float(w['anon_pending']) > 0.0:
            wf['anon_pending'] = w['anon_pending']

    checkAddressesOwned(swap_client, ci, wf)
    return wf


def page_wallets(self, url_split, post_string):
    server = self.server
    swap_client = server.swap_client
    swap_client.checkSystemStatus()
    summary = swap_client.getSummary()

    messages = []
    err_messages = []

    swap_client.updateWalletsInfo()
    wallets = swap_client.getCachedWalletsInfo()

    wallets_formatted = []
    sk = sorted(wallets.keys())

    for k in sk:
        w = wallets[k]
        if 'error' in w:
            wallets_formatted.append({
                'cid': str(int(k)),
                'error': w['error']
            })
            continue

        if 'no_data' in w:
            wallets_formatted.append({
                'name': w['name'],
                'havedata': False,
                'updating': w['updating'],
            })
            continue

        ci = swap_client.ci(k)
        wf = format_wallet_data(swap_client, ci, w)

        wallets_formatted.append(wf)

    template = server.env.get_template('wallets.html')
    return self.render_template(template, {
        'messages': messages,
        'err_messages': err_messages,
        'wallets': wallets_formatted,
        'summary': summary,
    })


def page_wallet(self, url_split, post_string):
    ensure(len(url_split) > 2, 'Wallet not specified')
    wallet_ticker = url_split[2]
    server = self.server
    swap_client = server.swap_client
    swap_client.checkSystemStatus()
    summary = swap_client.getSummary()

    coin_id = getCoinIdFromTicker(wallet_ticker)

    page_data = {}
    messages = []
    err_messages = []
    show_utxo_groups = False
    form_data = self.checkForm(post_string, 'wallet', err_messages)
    if form_data:
        cid = str(int(coin_id))

        if bytes('newaddr_' + cid, 'utf-8') in form_data:
            swap_client.cacheNewAddressForCoin(coin_id)
        elif bytes('reseed_' + cid, 'utf-8') in form_data:
            try:
                swap_client.reseedWallet(coin_id)
                messages.append('Reseed complete ' + str(coin_id))
            except Exception as ex:
                err_messages.append('Reseed failed ' + str(ex))
            swap_client.updateWalletsInfo(True, coin_id)
        elif bytes('withdraw_' + cid, 'utf-8') in form_data:
            try:
                value = form_data[bytes('amt_' + cid, 'utf-8')][0].decode('utf-8')
                page_data['wd_value_' + cid] = value
            except Exception as e:
                err_messages.append('Missing value')
            try:
                address = form_data[bytes('to_' + cid, 'utf-8')][0].decode('utf-8')
                page_data['wd_address_' + cid] = address
            except Exception as e:
                err_messages.append('Missing address')

            subfee = True if bytes('subfee_' + cid, 'utf-8') in form_data else False
            page_data['wd_subfee_' + cid] = subfee

            if coin_id == Coins.PART:
                try:
                    type_from = form_data[bytes('withdraw_type_from_' + cid, 'utf-8')][0].decode('utf-8')
                    type_to = form_data[bytes('withdraw_type_to_' + cid, 'utf-8')][0].decode('utf-8')
                    page_data['wd_type_from_' + cid] = type_from
                    page_data['wd_type_to_' + cid] = type_to
                except Exception as e:
                    err_messages.append('Missing type')

            if len(messages) == 0:
                ci = swap_client.ci(coin_id)
                ticker = ci.ticker()
                if coin_id == Coins.PART:
                    try:
                        txid = swap_client.withdrawParticl(type_from, type_to, value, address, subfee)
                        messages.append('Withdrew {} {} ({} to {}) to address {}<br/>In txid: {}'.format(value, ticker, type_from, type_to, address, txid))
                    except Exception as e:
                        err_messages.append(str(e))
                else:
                    try:
                        txid = swap_client.withdrawCoin(coin_id, value, address, subfee)
                        messages.append('Withdrew {} {} to address {}<br/>In txid: {}'.format(value, ticker, address, txid))
                    except Exception as e:
                        err_messages.append(str(e))
                swap_client.updateWalletsInfo(True, coin_id)
        elif have_data_entry(form_data, 'showutxogroups'):
            show_utxo_groups = True
        elif have_data_entry(form_data, 'create_utxo'):
            show_utxo_groups = True
            try:
                value = get_data_entry(form_data, 'utxo_value')
                page_data['utxo_value'] = value

                ci = swap_client.ci(coin_id)

                value_sats = ci.make_int(value)

                txid, address = ci.createUTXO(value_sats)
                messages.append('Created new utxo of value {} and address {}<br/>In txid: {}'.format(value, address, txid))
            except Exception as e:
                err_messages.append(str(e))
                if swap_client.debug is True:
                    swap_client.log.error(traceback.format_exc())

    swap_client.updateWalletsInfo(only_coin=coin_id, wait_for_complete=True)
    wallets = swap_client.getCachedWalletsInfo({'coin_id': coin_id})
    for k in wallets.keys():
        w = wallets[k]
        if 'error' in w:
            wallet_data = {
                'cid': str(int(k)),
                'error': w['error']
            }
            continue

        if 'no_data' in w:
            wallet_data = {
                'name': w['name'],
                'havedata': False,
                'updating': w['updating'],
            }
            continue

        ci = swap_client.ci(k)
        cid = str(int(coin_id))

        wallet_data = format_wallet_data(swap_client, ci, w)

        fee_rate, fee_src = swap_client.getFeeRateForCoin(k)
        est_fee = swap_client.estimateWithdrawFee(k, fee_rate)
        wallet_data['fee_rate'] = ci.format_amount(int(fee_rate * ci.COIN()))
        wallet_data['fee_rate_src'] = fee_src
        wallet_data['est_fee'] = 'Unknown' if est_fee is None else ci.format_amount(int(est_fee * ci.COIN()))
        wallet_data['deposit_address'] = w.get('deposit_address', 'Refresh necessary')

        if k == Coins.XMR:
            wallet_data['main_address'] = w.get('main_address', 'Refresh necessary')

        if 'wd_type_from_' + cid in page_data:
            wallet_data['wd_type_from'] = page_data['wd_type_from_' + cid]
        if 'wd_type_to_' + cid in page_data:
            wallet_data['wd_type_to'] = page_data['wd_type_to_' + cid]

        if 'wd_value_' + cid in page_data:
            wallet_data['wd_value'] = page_data['wd_value_' + cid]
        if 'wd_address_' + cid in page_data:
            wallet_data['wd_address'] = page_data['wd_address_' + cid]
        if 'wd_subfee_' + cid in page_data:
            wallet_data['wd_subfee'] = page_data['wd_subfee_' + cid]
        if 'utxo_value' in page_data:
            wallet_data['utxo_value'] = page_data['utxo_value']

        if show_utxo_groups:
            utxo_groups = ''
            unspent_by_addr = ci.getUnspentsByAddr()

            sorted_unspent_by_addr = sorted(unspent_by_addr.items(), key=lambda x: x[1], reverse=True)
            for kv in sorted_unspent_by_addr:
                utxo_groups += kv[0] + ' ' + ci.format_amount(kv[1]) + '\n'

            wallet_data['show_utxo_groups'] = True
            wallet_data['utxo_groups'] = utxo_groups

        checkAddressesOwned(swap_client, ci, wallet_data)

    template = server.env.get_template('wallet.html')
    return self.render_template(template, {
        'messages': messages,
        'err_messages': err_messages,
        'w': wallet_data,
        'summary': summary,
        'block_unknown_seeds': swap_client._restrict_unknown_seed_wallets,
    })
