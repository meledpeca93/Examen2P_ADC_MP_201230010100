from django.urls import path

from . import views


urlpatterns = [
    path("", views.order_list, name="order_list"),
    path("ordenes/nueva/", views.order_create, name="order_create"),
    path("ordenes/<int:order_id>/", views.order_detail, name="order_detail"),
    path("ordenes/<int:order_id>/editar/", views.order_edit, name="order_edit"),
    path("ordenes/<int:order_id>/eliminar/", views.order_delete, name="order_delete"),
    path(
        "ordenes/<int:order_id>/detalles/nuevo/",
        views.detail_create,
        name="detail_create",
    ),
    path(
        "ordenes/<int:order_id>/detalles/<int:detail_id>/editar/",
        views.detail_edit,
        name="detail_edit",
    ),
    path(
        "ordenes/<int:order_id>/detalles/<int:detail_id>/eliminar/",
        views.detail_delete,
        name="detail_delete",
    ),
]