from django.contrib import messages
from django.http import HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.urls import reverse

from .api_client import APIError, api_request
from .forms import DetailForm, OrderForm


def _render_order_list(request, form=None, show_create_modal=False):
    try:
        orders = api_request("GET", "/api/ordenes")
    except APIError as exc:
        messages.error(request, str(exc))
        orders = None
    return render(
        request,
        "portal/order_list.html",
        {
            "orders": orders,
            "form": form if form is not None else OrderForm(),
            "show_create_modal": show_create_modal,
        },
    )


def order_list(request):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    return _render_order_list(
        request,
        show_create_modal=request.GET.get("new") == "1",
    )


def _get_order_for_detail(request, order_id):
    try:
        return api_request("GET", f"/api/ordenes/{order_id}")
    except APIError as exc:
        messages.error(request, str(exc))
        return None


def _render_order_detail(request, order_id, form=None, show_detail_modal=False):
    order = _get_order_for_detail(request, order_id)
    if order is None:
        return redirect("order_list")
    return render(
        request,
        "portal/order_detail.html",
        {
            "order": order,
            "detail_form": form if form is not None else DetailForm(),
            "show_detail_modal": show_detail_modal,
        },
    )


def order_detail(request, order_id):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    return _render_order_detail(
        request,
        order_id,
        show_detail_modal=request.GET.get("new_detail") == "1",
    )


def _order_payload(form):
    return {
        "cliente": form.cleaned_data["cliente"],
        "fecha": form.cleaned_data["fecha"].isoformat(),
        "estado": form.cleaned_data["estado"],
    }


def order_create(request):
    if request.method == "GET":
        return redirect(f"{reverse('order_list')}?new=1")
    if request.method != "POST":
        return HttpResponseNotAllowed(["GET", "POST"])

    form = OrderForm(request.POST)
    if not form.is_valid():
        return _render_order_list(request, form=form, show_create_modal=True)

    try:
        order = api_request("POST", "/api/ordenes", _order_payload(form))
    except APIError as exc:
        messages.error(request, str(exc))
        return _render_order_list(request, form=form, show_create_modal=True)

    messages.success(request, "La orden se creó correctamente.")
    return redirect("order_detail", order_id=order["id"])


def order_edit(request, order_id):
    try:
        order = api_request("GET", f"/api/ordenes/{order_id}")
    except APIError as exc:
        messages.error(request, str(exc))
        return redirect("order_list")

    initial = {
        "cliente": order["cliente"],
        "fecha": order["fecha"][:16],
        "estado": order["estado"],
    }
    form = OrderForm(
        request.POST if request.method == "POST" else None,
        initial=initial,
    )
    if request.method == "POST" and form.is_valid():
        try:
            api_request(
                "PUT",
                f"/api/ordenes/{order_id}",
                _order_payload(form),
            )
        except APIError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "La orden se actualizó correctamente.")
            return redirect("order_detail", order_id=order_id)
    return render(
        request,
        "portal/order_form.html",
        {"form": form, "title": "Editar orden"},
    )


def order_delete(request, order_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    try:
        api_request("DELETE", f"/api/ordenes/{order_id}")
    except APIError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "La orden y sus detalles se eliminaron.")
    return redirect("order_list")


def _detail_payload(form):
    return {
        "producto": form.cleaned_data["producto"],
        "cantidad": form.cleaned_data["cantidad"],
        "precio_unitario": float(form.cleaned_data["precio_unitario"]),
    }


def detail_create(request, order_id):
    if request.method == "GET":
        return redirect(
            f"{reverse('order_detail', kwargs={'order_id': order_id})}?new_detail=1"
        )
    if request.method != "POST":
        return HttpResponseNotAllowed(["GET", "POST"])

    form = DetailForm(request.POST)
    if not form.is_valid():
        return _render_order_detail(
            request,
            order_id,
            form=form,
            show_detail_modal=True,
        )

    try:
        api_request(
            "POST",
            f"/api/ordenes/{order_id}/detalles",
            _detail_payload(form),
        )
    except APIError as exc:
        messages.error(request, str(exc))
        return _render_order_detail(
            request,
            order_id,
            form=form,
            show_detail_modal=True,
        )

    messages.success(request, "Detalle agregado; el total se recalculó.")
    return redirect("order_detail", order_id=order_id)


def detail_edit(request, order_id, detail_id):
    order = _get_order_for_detail(request, order_id)
    if order is None:
        return redirect("order_list")

    detail = next(
        (item for item in order["detalles"] if item["id"] == detail_id),
        None,
    )
    if detail is None:
        messages.error(
            request,
            f"El detalle {detail_id} no pertenece a la orden {order_id}.",
        )
        return redirect("order_detail", order_id=order_id)

    initial = {
        "producto": detail["producto"],
        "cantidad": detail["cantidad"],
        "precio_unitario": detail["precio_unitario"],
    }
    form = DetailForm(
        request.POST if request.method == "POST" else None,
        initial=initial,
    )
    if request.method == "POST" and form.is_valid():
        try:
            api_request(
                "PUT",
                f"/api/detalles/{detail_id}",
                _detail_payload(form),
            )
        except APIError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Detalle actualizado; el total se recalculó.")
            return redirect("order_detail", order_id=order_id)
    return render(
        request,
        "portal/detail_form.html",
        {"form": form, "title": "Editar detalle", "order": order},
    )


def detail_delete(request, order_id, detail_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    order = _get_order_for_detail(request, order_id)
    if order is None:
        return redirect("order_list")
    if not any(item["id"] == detail_id for item in order["detalles"]):
        messages.error(
            request,
            f"El detalle {detail_id} no pertenece a la orden {order_id}.",
        )
        return redirect("order_detail", order_id=order_id)

    try:
        api_request("DELETE", f"/api/detalles/{detail_id}")
    except APIError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Detalle eliminado; el total se recalculó.")
    return redirect("order_detail", order_id=order_id)