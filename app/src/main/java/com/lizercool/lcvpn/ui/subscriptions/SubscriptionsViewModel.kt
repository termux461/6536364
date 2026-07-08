package com.lizercool.lcvpn.ui.subscriptions

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.lizercool.lcvpn.data.db.AppDatabase
import com.lizercool.lcvpn.data.db.entity.SubscriptionEntity
import com.lizercool.lcvpn.network.subscription.SubscriptionRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

class SubscriptionsViewModel(application: Application) : AndroidViewModel(application) {

    private val db = AppDatabase.get(application)
    private val repository = SubscriptionRepository(db.subscriptionDao(), db.serverDao(), application)

    val subscriptions: StateFlow<List<SubscriptionEntity>> = db.subscriptionDao().observeAll()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    private val _refreshingIds = MutableStateFlow<Set<Long>>(emptySet())
    val refreshingIds: StateFlow<Set<Long>> = _refreshingIds

    fun addSubscription(name: String, url: String, isReserve: Boolean) {
        viewModelScope.launch {
            val id = db.subscriptionDao().insert(
                SubscriptionEntity(name = name, url = url, isReserve = isReserve),
            )
            if (!isReserve) {
                db.subscriptionDao().byId(id)?.let { repository.refreshOne(it) }
            }
        }
    }

    fun updateSubscription(subscription: SubscriptionEntity) {
        viewModelScope.launch { db.subscriptionDao().update(subscription) }
    }

    fun deleteSubscription(subscription: SubscriptionEntity) {
        viewModelScope.launch {
            db.serverDao().deleteBySubscription(subscription.id)
            db.subscriptionDao().delete(subscription)
        }
    }

    fun refresh(subscription: SubscriptionEntity) {
        viewModelScope.launch {
            _refreshingIds.value = _refreshingIds.value + subscription.id
            repository.refreshOne(subscription)
            _refreshingIds.value = _refreshingIds.value - subscription.id
        }
    }
}
